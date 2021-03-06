#! /usr/bin/python
# vim:ts=4:sw=4:ai:et:si:sts=4:fileencoding=utf-8
import time
import cgi
import datetime
import json
from channel import BaseChannel, ChannelException,ChannelMetaClass, STATUS_BAD, STATUS_GOOD, STATUS_UGLY
from utils import *
import httplib
#import xbmcplugin
#import xbmc
try:
    from pyamf import remoting
    has_pyamf = True
except ImportError:
    has_pyamf = False
import logging

logger = logging.getLogger(__name__)

class ThePlatformBaseChannel(BaseChannel):
    is_abstract = True
    base_url = None
    PID = None
    category_cache_timeout = 60 # value is in seconds. so 5 minutes.

    def get_categories_json(self):
        return self.base_url + 'getCategoryList?PID=%s'%(self.PID) + \
            '&field=ID&field=depth&field=title&field=description&field=hasReleases&field=fullTitle&field=thumbnailURL&field=hasChildren'

    def get_releases_json(self):
        return self.base_url + 'getReleaseList?PID=%s'%(self.PID) + \
            '&field=title&field=PID&field=ID&field=description&field=categoryIDs&field=thumbnailURL&field=URL&field=airdate&field=length&field=bitrate' + \
            '&sortField=airdate&sortDescending=true&startIndex=1&endIndex=100'



    def parse_callback(self, body):
        logger.debug('parse_callback body %s:' % body)
        return json.loads(body)


    def get_cache_key(self):
        return self.short_name

    def get_cached_categories(self, parent_id):

        categories = None

        fpath = os.path.join(self.plugin.get_cache_dir(), 'canada.on.demand.%s.categories.cache' % (self.get_cache_key(),))
        try:
            if os.path.exists(fpath):
                with open(fpath) as fh:
                    data = json.loads(f.read())
                if data['cached_at'] + self.category_cache_timeout >= time.time():
                    logger.debug("using cached Categories")
                    categories = data['categories']
        except:
            logger.debug("no cached Categories path")

        if not categories:
            logger.debug('http-retrieving categories')
            url = self.get_categories_json(parent_id)
            logger.debug('get_cached_categories(p_id=%s) url=%s'%(parent_id, url))

            categories = self.parse_callback(self.plugin.fetch(url, self.cache_timeout).read())['items']
            if self.category_cache_timeout > 0:
                fpath = os.path.join(self.plugin.get_cache_dir(), 'canada.on.demand.%s.categories.cache' % (self.short_name,))
                with open(fpath, 'w') as fh:
                    fh.write(json.dumps({'cached_at': time.time(), 'categories': categories}))

        return categories


    def get_categories(self, parent_id=None):

        categories = self.get_cached_categories(parent_id)

        #needs to be defined by sub-class:
        #  - CBC does an actual drill-down on parentId
        #  - Canwest uses string-matching on the fullTitle field
        categories = self.get_child_categories(categories, parent_id)

        cats = []
        for c in categories:
            #logger.debug(c)
            data = {}
            data.update(self.args)
            data.update({
                'entry_id': c['ID'],
                'Thumb': c['thumbnailURL'],
                'Title': c['title'],
                'Plot': c['description'],
                'action': 'browse',
                'force_cache_update': False,
                'hasReleases': c['hasReleases'],
                'hasChildren': c['hasChildren'],
                'depth': c['depth']
            })

            #cbc-only, so check if key is present on other providers (Canwest)
            if 'customData' in c:
                for dict in c['customData']:
                    if dict['value']:
                        #if dict['value'] == '(not specified)':
                            #dict['value'] = "''"
                        #if dict['value'] != '':
                        data.update({dict['title']: dict['value']},) #urlquoteval(dict['value'])

            cats.append(data)

        # for CBC: sort categories (assumes that GroupLevel won't exceed 100000)
        cats.sort(key=lambda x: int(x.get('GroupLevel', 0))*100000+int(x.get('GroupOrder', 0)))

        logger.debug("get_categories cats=%s"%cats)
        return cats


    def get_releases(self, parameter): #category_id for Canwest, a customData dict for CBC
        logger.debug('get_releases (parameter=%s)'%parameter)

        url = self.get_releases_json(parameter) #has a %s in it--  Canwest:a real cat_id, CBC: the customTags,
        logger.debug('get_releases url=%s'%url)

        data = self.parse_callback(self.plugin.fetch(url, max_age=self.cache_timeout).read())
        max_bitrate = int(self.plugin.get_setting('max_bitrate'))

        rels = []
        for item in data['items']:
            item['bitrate'] = int(item['bitrate'])/1024
            item_date = time.strftime('%d.%m.%Y', time.localtime(item['airdate']/1000))
            if (not rels) or (rels[-1]['Title'] != item['title']) or (rels[-1]['medialen'] != item['length']):

                action = 'play_episode'

                rels.append({
                    'Thumb': item['thumbnailURL'],
                    'Title': item['title'],
                    'Plot': item['description'],
                    'Date': item_date,
                    'entry_id': item['ID'],
                    'remote_url': item['URL'],
                    'remote_PID': item['PID'],
                    'channel': self.args['channel'],
                    'station': self.long_name,
                    'action': action,
                    'bitrate': item['bitrate'],
                    'medialen' : item['length']
                })

            else:
                if item['bitrate'] <= max_bitrate and item['bitrate'] > rels[-1]['bitrate']:
                    rels.pop()
                    action = 'play_episode'

                    rels.append({
                        'Thumb': item['thumbnailURL'],
                        'Title': item['title'],
                        'Plot': item['description'],
                        'Date': item_date,
                        'entry_id': item['ID'],
                        'remote_url': item['URL'],
                        'remote_PID': item['PID'],
                        'channel': self.args['channel'],
                        'station': self.long_name,
                        'action': action,
                        'bitrate': item['bitrate'],
                        'medialen': item['length']
                    })


        return rels


    def action_root(self):
        logger.debug('ThePlatformBaseChannel::action_root')
        parent_id = self.args.get('entry_id', None) # this should be None from @classmethod
        items = []
        if parent_id == 'None':
            parent_id = None
        categories = self.get_categories(parent_id)# and root=true
        for cat in categories:
            items.append(self.plugin.add_list_item(cat))
        return items
#        self.plugin.end_list()


    def action_browse(self):
        """
        Handles the majority of the navigation.

        """
        parent_id = self.args['entry_id']

        categories = self.get_categories(parent_id)
        logger.debug("Got %s Categories: %s" % (len(categories), "\n".join(repr(c) for c in categories)))

        items = []
        if categories:
            for cat in categories:
                items.append(self.plugin.add_list_item(cat))
#            self.plugin.end_list()
        else:
            # only add releases if no categories
            releases = self.get_releases(self.args)
            logger.debug("Got %s Releases: %s" % (len(releases), "\n".join(repr(r) for r in releases)))
            for rel in releases:
                items.append(self.plugin.add_list_item(rel, is_folder=False))
#            self.plugin.end_list('episodes', [xbmcplugin.SORT_METHOD_DATE])
        return items

    def get_episode_list_data(self, remote_pid):
        url = 'http://release.theplatform.com/content.select?&pid=%s&format=SMIL&mbr=true' % (remote_pid,)
        # do not cache this!!!
        soup = BeautifulStoneSoup(self.plugin.fetch(url))
        logger.debug("SOUP: %s" % (soup,))
        results = []

        for i, ref in enumerate(soup.findAll('ref')):
            base_url = ''
            playpath = None

            # skip the ads
            if ref['src'].startswith('pfadx///'):
                continue

            if ref['src'].startswith('rtmp://'): #all other channels type of SMIL
            #the meta base="http:// is actually the prefix to an adserver
                try:
                    base_url, playpath = decode_htmlentities(ref['src']).split('<break>', 1) #<break>
                except ValueError:
                    base_url = decode_htmlentities(ref['src'])
                    playpath = None
                logger.debug('all other channels type of SMIL  base_url=%s  playpath=%s'%(base_url, playpath))
            elif ref['src'].startswith('rtmpe://') :
                try:
                    base_url, playpath = decode_htmlentities(ref['src']).split('{break}', 1) #<break>
                    logger.debug("RTMPE? ref= %s, base_url = %s, playpath = %s" %(ref['src'], base_url, playpath))
                except ValueError:
                    base_url = decode_htmlentities(ref['src'])
                    playpath = None
                logger.debug("RTMPE ref= %s, base_url = %s, playpath = %s" %(ref['src'], base_url, playpath))
            elif soup.meta['base'].startswith('rtmp://'): #CBC type of SMIL
                base_url = decode_htmlentities(soup.meta['base'])
                playpath = ref['src']
                logger.debug('CBC type of SMIL  base_url=%s  playpath=%s'%(base_url, playpath))
            elif soup.meta['base'].startswith('http://'): #CBC type of SMIL
                if re.search(r'doubleclick\.net', soup.meta['base']):
                    # We don't need no steenking ads!
                    continue
                base_url = decode_htmlentities(soup.meta['base'])
                playpath = ref['src']
                logger.debug('CBC type of SMIL  base_url=%s  playpath=%s'%(base_url, playpath))
            elif soup.meta['base'].startswith('{manifest:none}rtmp://'): # New CBC type of SMIL
                base_url = decode_htmlentities(soup.meta['base'][15:])
                playpath = ref['src']
                playpath = playpath[0:playpath.find("{manifest")]
                logger.debug('CBC type of SMIL  base_url=%s  playpath=%s'%(base_url, playpath))
            elif soup.meta['base'].startswith('{switch:none}{manifest:none}rtmp://'): # New CBC type of SMIL
                base_url = decode_htmlentities(soup.meta['base'][28:])
                playpath = ref['src']
                playpath = playpath[0:playpath.find("{manifest")]
                logger.debug('CBC type of SMIL  base_url=%s  playpath=%s'%(base_url, playpath))
            else:
                continue

            qs = None
            try:
                base_url, qs = base_url.split("?",1)
            except ValueError:
                base_url = base_url

            logger.debug({'base_url': base_url, 'playpath': playpath, 'qs': qs, })

            clip_url = base_url
            if playpath:
                clip_url += playpath
            if qs:
                clip_url += "?" + qs

            data = {}
            data.update(self.args)
            data['Title'] = self.args['Title']# + " clip %s" % (i+1,)
            data['clip_url'] = clip_url
            data['action'] = 'play'
            results.append(data)
        return results

    def action_play_episode(self):
        items = self.get_episode_list_data(self.args['remote_PID'])
        print items
        if len(items) != 1: raise RuntimeError('theplatform len(items) should be 1')
        parse = URLParser(swf_url=self.swf_url)
        return self.plugin.set_stream_url(parse(items[0]['clip_url']))

    @classmethod
    def get_channel_entry_info(self):
        """
        This method is responsible for returning the info
        used to generate the Channel listitem at the plugin's
        root level.

        """
        return {
            'Title': self.long_name,
            'Thumb': self.icon_path,
            'action': 'root',
            'entry_id': None,
            'channel': self.short_name,
            'force_cache_update': True,
        }




class CBCChannel(ThePlatformBaseChannel):
    PID = "_DyE_l_gC9yXF9BvDQ4XNfcCVLS4PQij"
    base_url = 'http://cbc.feeds.theplatform.com/ps/JSON/PortalService/2.2/'
    swf_url = 'https://livepassdl.conviva.com/hf/ver/2.82.0.19087/LivePassModuleMain_osmf.swf'
    custom_fields = ['Account','AudioVideo','BylineCredit','CBCPersonalities','Characters','ClipType',
        'EpisodeNumber','Event','Genre','LiveOnDemand','Organizations','People','Producers','Region',
        'Segment','Show','SeasonNumber','Sport','SubEvent']
    status = STATUS_UGLY
    short_name = 'cbc'
    long_name = 'CBC'
    category_cache_timeout = 0 # can't cache for CBC, need to drill-down each time

    #this holds an initial value for CBC only to get the top-level categories;
    #it is overwritten in action_root
    in_root = False
    category_json = '&query=ParentIDs|'

    def get_categories_json(self, arg):
        logger.debug('get_categories_json arg=%s, categ_json=%s'%(arg, self.category_json))
        url = ThePlatformBaseChannel.get_categories_json(self) + \
            '&customField=GroupLevel&customField=GroupOrder&customField=IsDynamicPlaylist'

        # Add other custom fields
        for cf in self.custom_fields:
            url += '&customField=' + cf

        if arg or self.in_root:
            url += self.category_json
        if arg:
            url += arg
        return url

    #arg is CBC's customfield array from getReleases query
    def get_releases_json(self,arg):
        url = ThePlatformBaseChannel.get_releases_json(self)
        logger.warn("RELURL: %s" % (url,))

        # this code is copied from CBCVideoFunctions.js on CBC's web site
        if arg['IsDynamicPlaylist'] and arg['IsDynamicPlaylist'].lower() != 'false':
            for cf in self.custom_fields:
                if cf in arg and arg[cf] != '(not specified)' and (cf!='Genre' or arg[cf]!='Other'):
                    url += '&query=ContentCustomText|%s|%s' % (cf, urlquoteval(arg[cf]))
        else:
            url += '&query=CategoryIds|%s' % urlquoteval(arg['entry_id'])

        logger.debug('get_releases_json: %s'%url)
        return url

    def get_child_categories(self, categorylist, parent_id):
        if parent_id is None:
            categories = [c for c in categorylist \
                          #if c['depth'] == 1 or c['depth'] == 0
                          if c['depth'] == 0
                          and (
                              self.plugin.get_setting('show_empty_cat') == True
                              or (c['hasReleases'] or c['hasChildren'])
                          )]
        else:
            #do nothing with parent_id in CBC's case
            categories = categorylist
        return categories

    def action_root(self):
        logger.debug('CBCChannel::action_root')

        #all CBC sections = ['Shows,Sports,News,Kids,Radio']
        self.category_json = ''
        self.in_root = True #just for annoying old CBC
        self.category_json = '&query=FullTitles|Shows,Sports,News,Radio'
        categories = self.get_categories(None)

        items = []
        for cat in categories:
            cat.update({'Title': 'CBC %s'%cat['Title']})
            items.append(self.plugin.add_list_item(cat))
#        self.plugin.end_list()

        #restore ParentIDs query for sub-categories
        self.category_json = '&query=ParentIDs|'
        self.in_root = False
        logger.debug('setting categ_json=%s'%self.category_json)
        return items


#class TouTV(ThePlatformBaseChannel):
#    long_name = 'Tou.TV'
#    short_name='toutv'
#    base_url = 'http://www.tou.tv/repertoire/'
#    swf_url = 'http://static.tou.tv/lib/ThePlatform/4.2.9c/swf/flvPlayer.swf'
#    default_action = 'root'
#
#    categories = [
#            ("animation","Animation"),
#            ("entrevues-varietes", "Entrevues et varietes"),
#            ("films-documentaires","Films et documentaires"),
#            ("magazines-affaires-publiques", "Magazines et affaires publiques"),
#            ("series-teleromans", "Series et teleromans"),
#            ("spectacles-evenements", "Spectacles et evenements"),
#            ("webteles",u"Webteles"),
#    ]
#
#    def action_play_episode(self):
#        url = self.args['remote_url']
#        soup = BeautifulSoup(self.plugin.fetch(url, max_age=self.cache_timeout))
#        scripts = soup.findAll('script')
#
#        epinfo_tag = [s for s in scripts if s.contents and s.contents[0].strip().startswith("// Get IP address and episode ID")][0]
#        self.args['remote_PID'] = re.search(r"episodeId = '([^']+)'", epinfo_tag.contents[0].strip()).groups()[0]
#        return ThePlatformBaseChannel.action_play_episode(self)
#
#    def action_browse_series(self):
#        url = self.args['remote_url']
#        soup = BeautifulSoup(self.plugin.fetch(url,max_age=self.cache_timeout))
#        for row in soup.findAll('div', {'class': 'blocepisodeemission'}):
#
#            data = {}
#            data.update(self.args)
#            images = row.findAll('img')
#            if len(images) == 2:
#                image = images[1]
#            else:
#                image = images[0]
#
#            title = decode_htmlentities(row.find('a', {'class': 'episode'}).b.contents[0],)[:-1]
#
#            try:
#                seasonp = [p for p in row.findAll('p') if 'class' in dict(p.attrs)][0]
#                season = seasonp.contents[0].strip()
#                title = season + ": " + title
#            except:
#                pass
#
#            try:
#                plotp = [p for p in row.findAll('p') if 'class' not in dict(p.attrs)][0]
#                plot = plotp.contents[0].strip()
#            except:
#                plot = '(failed to fetch plot)'
#
#            data.update({
#                'action': 'play_episode',
#                'remote_url': 'http://tou.tv' + row.find('a')['href'],
#                'Title': title,
#                'Thumb': image['src'],
#                'Plot': plot
#            })
#            self.plugin.add_list_item(data, is_folder=False)
#        self.plugin.end_list('episodes')
#
#    def action_browse_category(self):
#        cat = dict(self.categories)[self.args['category']]
#        logger.debug("CAT: %s" % (cat,))
#        url = self.base_url + self.args['category'] + "/"
#        soup = BeautifulSoup(self.plugin.fetch(url,max_age=self.cache_timeout))
#        logger.debug(url)
#        for a in soup.findAll('a', {'class': re.compile(r'bloc_contenu.*')}):
#            data = {}
#            data.update(self.args)
#            data.update({
#                'action': 'browse_series',
#                'remote_url': 'http://tou.tv' + a['href'],
#                'Title': a.find('h1').contents[0],
#            })
#
#            self.plugin.add_list_item(data)
#        self.plugin.end_list()
#
#    def action_root(self):
#
#        for cat in self.categories:
#            data = {}
#            data.update(self.args)
#            data.update({
#                'channel': 'toutv',
#                'action': 'browse_category',
#                'category': cat[0],
#                'Title': cat[1],
#            })
#
#            self.plugin.add_list_item(data)
#        self.plugin.end_list()


