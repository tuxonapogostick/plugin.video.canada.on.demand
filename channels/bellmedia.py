#! /usr/bin/python
# vim:ts=4:sw=4:ai:et:si:sts=4:fileencoding=utf-8

from theplatform import *
from BeautifulSoup import BeautifulStoneSoup
import yaml
import json

try:
    from pyamf import remoting
    has_pyamf = True
except ImportError:
    has_pyamf = False

import logging

logger = logging.getLogger(__name__)

BASEDIR = "/opt/prf/persist/canada"
CONFIGDIR = BASEDIR + "/config"
CONFIGFILE = CONFIGDIR + "/plugin.conf"

class BellMediaBaseChannel(BaseChannel):
    status = STATUS_GOOD
    is_abstract = True
    default_action = 'root'
    swf_url = 'http://player.9c9media.com/ETS_Universal_42_1.6/etsmediaplayer/bm_mediaplayer.swf'
    videohubBase = "http://components.bellmedia.ca/videohub"
    settings_js = videohubBase + "/js/settings/%s/settings.js"
    detailsBase = "http://capi.9c9media.com/destinations/%s/platforms/desktop"
    collection_json = detailsBase + "/collections/%d"
    media_group_json = collection_json + "/medias"
    media_group_json_include = "[id,images,name,type]"
    medias_json = detailsBase + "/medias/%d/contents"
    contents_json = collection_json + "/contents"
    contents_json_include = "[authentication,broadcastdate,broadcasttime,contentpackages,desc,episode,id,images,media,name,runtime,season,shortdesc,type]"
    json_qs = "?$include=%s&$page=%d$top=25&$inlinecount=&Images.Type=thumbnail"
    stacks_json = detailsBase + '/contents/%d/contentpackages/%d/stacks'
    user_agent = 'Mozilla/5.0 (iPhone; U; CPU iPhone OS 4_3_2 like Mac OS X; en-us) AppleWebKit/533.17.9 (KHTML, like Gecko) Version/5.0.2 Mobile/8H7 Safari/653.18.5'

    def action_root(self):
        url = self.settings_js % self.brandId
        with self.plugin.fetch(url, max_age=self.cache_timeout,
                               user_agent=self.user_agent) as f:
            jsonp = f.read()
        jsonp = jsonp[jsonp.index("(") + 1 : jsonp.rindex(")")]
        jsonp = jsonp.replace("\t", "        ")

        settings = None
        try:
            settings = json.loads(jsonp)
        except Exception as e:
            print e
            pass

        if not settings:
            try:
                settings = yaml.load(jsonp)
            except Exception as e:
                print 3
                pass
        if not settings:
            return []

        items = []
        for widget in settings['widgets']:
            if widget['type'] == "collection-list":
                for item in widget['items']:
                    data = {}
                    data.update(self.args)
                    data['Title'] = item['text']
                    data['action'] = 'browse_%s' % item['collection']['type']
                    data['entry_id'] = item['collection']['id']
                    items.append(self.plugin.add_list_item(data))
            elif widget['type'] == "expand-collection-list":
                for item in widget['items']:
                    if item['text'] != "View by Show Name":
                        continue
                    data = {}
                    data.update(self.args)
                    data['Title'] = widget['text']
                    data['action'] = 'browse_%s_group' % item['apiReturnType']
                    m = re.match(r'collections/(\d+)/medias', item['apiUrl'])
                    if not m:
                        continue
                    data['entry_id'] = int(m.group(1))
                    items.append(self.plugin.add_list_item(data))
        return items

    def action_browse_media(self):
        return self.action_browse_common_content(self.medias_json, 'video_id')

    def action_browse_content(self):
        return self.action_browse_common_content(self.contents_json, 'entry_id')

    def action_browse_common_content(self, baseUrl, idName):
        baseUrl = baseUrl + self.json_qs
        items = []
        page = 1
        while True:
            url = baseUrl % (self.destination, int(self.args[idName]),
                             self.contents_json_include, page)
            with self.plugin.fetch(url, max_age=self.cache_timeout,
                                   user_agent=self.user_agent) as f:
                jsonString = f.read()
            metadata = json.loads(jsonString)

            print metadata
            count = metadata['Count']
            for item in metadata['Items']:
                if item['Authentication']['Required']:
                    continue
                data = {}
                data['entry_id'] = item['Id']
                data['Episode'] = item['Name']
                data['Plot'] = item['Desc']
                data['action'] = 'play_episode'
                data['video_id'] = item['Media']['Id']
                data['Title'] = item['Media']['Name']
                data['Thumb'] = item['Media']['Images'][0]['Url']
                data['seasonnum'] = item['Season']['Number']
                data['episodenum'] = item['Episode']
                data['Date'] = item['BroadcastDate'] + " " + \
                               item['BroadcastTime'] + " EST5EDT"
                data['content_id'] = item['ContentPackages'][0]['Id']
                data['duration'] = item['ContentPackages'][0]['Duration']
                data['station'] = self.long_name
                data['channel'] = self.args['channel']
                items.append(self.plugin.add_list_item(data, is_folder=False))

            if count <= page * 25:
                break
            page += 1

        return items

    def action_browse_media_group(self):
        baseUrl = self.media_group_json + self.json_qs
        items = []
        page = 1
        while True:
            url = baseUrl % (self.destination, int(self.args['entry_id']),
                             self.media_group_json_include, page)
            with self.plugin.fetch(url, max_age=self.cache_timeout,
                                   user_agent=self.user_agent) as f:
                jsonString = f.read()
            metadata = json.loads(jsonString)

            print metadata
            count = metadata['Count']
            for item in metadata['Items']:
                data = {}
                data.update(self.args)
                data['video_id'] = item['Id']
                data['ShowTitle'] = item['Name']
                data['action'] = 'browse_media'
                data['Thumb'] = item['Images'][0]['Url']
                items.append(self.plugin.add_list_item(data))

            if count <= page * 25:
                break
            page += 1

        return items

    def action_play_episode(self):
        url = self.stacks_json % (self.destination, int(self.args['video_id']),
                                  int(self.args['content_id']))
        return self.plugin.set_stream_url(url, self.args, "AdobeHDS")

class CTVNews(BellMediaBaseChannel):
    base_url = 'http://www.ctvnews.ca/video'
    short_name = 'ctvnews'
    long_name = 'CTV News'
    default_action = 'browse'

    def action_browse(self):
        if not self.args.get('remote_url', None):
            self.args['remote_url'] = self.base_url
        soup = BeautifulSoup(self.plugin.fetch(self.args['remote_url'], max_age=self.cache_timeout))

        items = []
        for category in soup.findAll('dt', 'videoPlaylistCategories'):
            data = {}
            data.update(self.args)
            data.update({
                'action': 'browse_category',
                'Title': category.a.contents[0],
                'entry_id': None,
                'category_id': category['id'],
                'page_num' : 1
            })
            items.append(self.plugin.add_list_item(data))
        return items
#        self.plugin.end_list()

    def action_browse_category(self):
        soup = BeautifulSoup(self.plugin.fetch("%s/%s?ot=example.AjaxPageLayout.ot&maxItemsPerPage=12&pageNum=%s"%(self.args['remote_url'],self.args["category_id"],self.args['page_num']),
                        max_age=self.cache_timeout))
        items = []
        for clip in soup.findAll('article'):
            thumb = None
            if clip.img.has_key('src'):
                thumb = clip.img['src']
            tagline = clip.h3.string
            #title = clip.find('p',{'class':'videoPlaylistDescription'}).string

            script = clip.findNextSibling()
            scripts = []
            while script:
                if script.name!='script': break;
                scripts.append(script)
                script = script.findNextSibling()

            if len(scripts)>2:
                script = scripts[0]
                txt = script.string.strip()
                if txt.find('playlistMap[')>=0:
                    match = re.search("playlistMap\['([0-9.]*)'\] = new Array()",txt)
                    playlist_id = match.group(1)
                    data = {}
                    data.update(self.args)
                    data.update({
                        'action': 'browse_playlist',
                        'Title': tagline,
                        'entry_id': None,
                        'Thumb': thumb,
                        'playlist_id': playlist_id,
                    })
                    items.append(self.plugin.add_list_item(data))
            else:
                for script in scripts:
                    txt = script.string.strip()
                    if txt.find('clip.id')>=0:
                        match = re.search('.*clip[.]id = ([0-9]*).*clip[.]title = "(.+?)".*clip[.]description = "(.*)"',txt,re.DOTALL)
                        clipId = match.group(1)
                        title = match.group(2).strip().decode('string-escape')
                        plot = match.group(3).strip()

                        data = {}
                        data.update(self.args)
                        data.update({
                            'Title': title.decode('unicode_escape'),
                            'action': 'play_clip',
                            'remote_url': clipId,
                            'clip_id': clipId,
                            'Thumb': thumb,
                            'tagline': tagline,
                            'plot': plot,
                            'genre': 'News'
                        })
                        items.append(self.plugin.add_list_item(data, is_folder=False))

        nextPager = soup.find("span", {"class":"videoPaginationNext"})
        if nextPager and nextPager.find('a'):
            data = {}
            data.update(self.args)
            data.update({
                'Title': ">>> Next Page",
                'page_num' : int(self.args["page_num"])+1
            })
        items.append(self.plugin.add_list_item(data))

        return items
#        self.plugin.end_list()

    def action_browse_playlist(self):
        soup = BeautifulSoup(self.plugin.fetch("%s/%s?ot=example.AjaxPageLayout.ot&maxItemsPerPage=12&pageNum=%s"%(self.args['remote_url'],self.args["playlist_id"],self.args['page_num']),
                        max_age=self.cache_timeout))
        items = []
        for clip in soup.findAll('article', {'class':'videoClipThumb'}):
            thumb = clip.img['src']
            tagline = clip.h3.a.string
            clipId = clip['id']
            plot = clip.p.string
            if plot: plot = plot.strip()
            data = {}
            data.update(self.args)
            data.update({
                'Title': tagline.decode('unicode_escape'),
                'action': 'play_clip',
                'remote_url': clipId,
                'clip_id': clipId,
                'Thumb': thumb,
                'tagline': tagline,
                'plot': plot,
                'genre': 'News'
            })
            items.append(self.plugin.add_list_item(data, is_folder=False))
        return items
#        self.plugin.end_list()

class CTVLocalNews(CTVNews):
    short_name = 'ctvlocal'
    long_name = 'CTV Local News'
    default_action = 'root'

    local_channels = [
        ('Atlantic', 'http://atlantic.ctvnews.ca/video'),
        ('Barrie', 'http://barrie.ctvnews.ca/video'),
        ('British Columbia', 'http://bc.ctvnews.ca/video'),
        ('Calgary', 'http://calgary.ctvnews.ca/video'),
        ('Edmonton', 'http://edmonton.ctvnews.ca/video'),
        ('Kitchener', 'http://kitchener.ctvnews.ca/video'),
        ('London', 'http://london.ctvnews.ca/video'),
        ('Montreal', 'http://montreal.ctvnews.ca/video'),
        ('Northern Ontario', 'http://northernontario.ctvnews.ca/video'),
        ('Ottawa', 'http://ottawa.ctvnews.ca/video'),
        ('Regina', 'http://regina.ctvnews.ca/video'),
        ('Saskatoon', 'http://saskatoon.ctvnews.ca/video'),
        ('Toronto', 'http://toronto.ctvnews.ca/video'),
        ('Windsor', 'http://windsor.ctvnews.ca/video'),
        ('Winnipeg', 'http://winnipeg.ctvnews.ca/video'),
        ('Vancouver Island', 'http://vancouverisland.ctvnews.ca/video'),
    ]


    def action_root(self):
        items = []
        for channel, domain in self.local_channels:
            items.append(self.plugin.add_list_item({
                'Title': channel,
                'action': 'browse',
                'channel': self.short_name,
                'entry_id': None,
                'local_channel': channel,
                'remote_url': domain,

                'Thumb': self.args['Thumb'],
            }))
        return items
#        self.plugin.end_list()


class Bravo(BellMediaBaseChannel):
    short_name = 'bravo'
    long_name = 'Bravo!'
    base_url = 'http://www.bravo.ca/video'
    brandId = 'bravo'
    destination = 'bravo_web'

class CTV(BellMediaBaseChannel):
    short_name = 'ctv'
    long_name = 'CTV'
    base_url = 'http://www.ctv.ca/video'
    brandId = 'ctv'
    destination = 'ctv_web'

class Discovery(BellMediaBaseChannel):
    short_name = 'discovery'
    long_name = 'Discovery'
    base_url = 'http://www.discovery.ca/video'
    brandId = 'discovery'
    destination = 'discovery_web'

class ComedyNetwork(BellMediaBaseChannel):
    short_name = 'comedynetwork'
    long_name = 'The Comedy Network'
    base_url = 'http://www.thecomedynetwork.ca/video'
    brandId = 'comedy'
    destination = 'comedy_web'

class Space(BellMediaBaseChannel):
    short_name = 'space'
    long_name = "Space"
    base_url = 'http://www.space.ca/video'
    brandId = 'space'
    destination = 'space_web'

# Missing settings.js file
#class BNN(BellMediaBaseChannel):
#    long_name = 'Business News Network'
#    short_name = 'bnn'
#    base_url = 'http://www.bnn.ca/video'
#    brandId = 'bnn'
#    destination = 'bnn_web'

class BellMediaOldBaseChannel(BaseChannel):
    status = STATUS_GOOD
    is_abstract = True
    root_url = 'VideoLibraryWithFrame.aspx'
    default_action = 'root'

    def action_root(self):
        url = self.base_url + self.root_url
        soup = BeautifulSoup(self.plugin.fetch(url, max_age=self.cache_timeout))
        ul = soup.find('div', {'id': 'Level1'}).find('ul')
        items = []
        for li in ul.findAll('li'):
            data = {}
            data.update(self.args)
            data['Title'] = decode_htmlentities(li.a['title'])
            data['action'] = 'browse_show'
            data['show_id'] = li.a['id']
            items.append(self.plugin.add_list_item(data))
        return items

    def action_browse(self):
        """
        DEPRECATED Bookmarks Shouldn't Use this..
        need to find a way to update user's bookmarks

        """
        rurl = self.args.get('remote_url', 'None')
        if rurl == 'None' or rurl is None:
            return self.action_root()

        logging.debug("RURL: %s" %(rurl.__class__,))
        show_id = re.findall(r"\&ShowID=(\d+)", rurl)
        if show_id:
            self.args['show_id'] = show_id[0]
            return self.action_browse_show()

        season_id = re.findall(r"\&SeasonID=(\d+)", rurl)
        if season_id:
            self.args['season_id'] = season_id[0]
            return self.action_browse_season()

        episode_id = re.findall(r"&EpisodeID=(\d+)", rurl)
        if episode_id:
            self.args['episode_id'] = eposode_id[0]
            return self.action_browse_episode()


    def action_browse_season(self):
        url = self.base_url + 'VideoLibraryContents.aspx?GetChildOnly=true&PanelID=3&SeasonID=%s&ForceParentShowID=%s' % (self.args['season_id'],self.args['show_id'])
        page = self.plugin.fetch(url, max_age=self.cache_timeout).read()
        soup = BeautifulStoneSoup(page)

        items = []
        for li in soup.find('ul').findAll('li'):
            a = li.find('a', {'id': re.compile('^Episode_\d+$')})

            data = {}
            data.update(self.args)
            data['episode_id'] = a['id'][8:]
            data['videocount'] = re.search("Interface\.GetChildPanel\('Episode',[ \d]+,([ \d]+),",a['onclick']).group(1)
            data['Title'] = a.text


            vc = int(data['videocount'])
            if vc == 1:
                action = 'play_episode'
            elif vc <= int(self.plugin.get_setting('max_playlist_size')) \
                and self.plugin.get_setting("make_playlists") == "true":
                action = 'play_episode'
            else:
                action = 'browse_episode'
            data['action'] = action
            if action == 'play_episode':
                data['station'] = self.long_name

            dl = li.find('dl', {'class':'Item'} )
            if dl:
                data['Plot'] = dl.find('dd', {'class':'Description'}).text
                data['Title'] = dl.find('dd', {'class':'Thumbnail'}).a['title']

                #m,d,y = ep['pubdate'].split("/")
                #data['Date'] = "%s.%s.%s" % (d,m,y)
                try:
                    data['Thumb'] = dl.find('dd', {'class':'Thumbnail'}).img['src']
                    pos = data['Thumb'].find('.jpg/80/60')
                    if pos!=-1:
                        data['Thumb'] = data['Thumb'][:pos]+'.jpg'
                except:
                    pass

            items.append(self.plugin.add_list_item(data, is_folder=(data['action']!='play_episode')))
        return items

    def action_play_episode(self):
        vidcount = self.args.get('videocount')
        if vidcount:
            vidcount = int(vidcount)

        items = []

        if vidcount  and vidcount == 1:
            data = list(self.iter_clip_list())[0]
            logging.debug(data)
            url = self.clipid_to_stream_url(data['clip_id'])
            return self.plugin.set_stream_url(url, data)
        else:
            for clipdata in self.iter_clip_list():
                url = self.plugin.get_url(clipdata)
                li = self.plugin.add_list_item(clipdata, is_folder=False, return_only=True)
                items.append(li)

            time.sleep(1)
            logging.debug("CLIPDATA: %s" % (playlist,))
            return items

    def iter_clip_list(self):
        start_offset = 1
        number_to_get = 12
        url_template = self.base_url + 'InfiniteScrollingContents.aspx?EpisodeID=%s&NumberToGet=%d&StartOffset=%d'
#        url = self.base_url + 'VideoLibraryContents.aspx?GetChildOnly=true&PanelID=4&EpisodeID=%s&ForceParentShowID=%s' % (self.args['episode_id'],self.args['show_id'])

        while True:
            url = url_template % (self.args['episode_id'],number_to_get,start_offset)
            page = self.plugin.fetch(url, max_age=self.cache_timeout)
            soup = BeautifulStoneSoup(page)
            start_offset += number_to_get

            clips = soup.findAll('li')
            if len(clips)==0:
                break

            for li in clips:
                text = li.dt.a['onclick']
                data = {}
                data.update(self.args)
                data['action'] = 'play_clip'
                data['Title'] = BeautifulSoup(li.dt.a.text,convertEntities=BeautifulSoup.HTML_ENTITIES).contents[0]
                try:
                    data['Title'] = re.search("Title:'([^'\\\\]*(\\\\.[^'\\\\]*)*)'",text).group(1).replace("\\'","'")
                    data['Thumb'] = re.search("EpisodeThumbnail:'([^'\\\\]*(\\\\.[^'\\\\]*)*)'",text).group(1)
                    data['Plot'] = re.search("Description:'([^'\\\\]*(\\\\.[^'\\\\]*)*)'",text).group(1)
                except:
                    pass
                data['clip_id'] = re.search("ClipId:'([^']+)'",text).group(1)
                yield data

    def action_browse_episode(self):
        logging.debug("ID: %s" % (self.args['episode_id'],))
        items = []
        for data in self.iter_clip_list():
            items.append(self.plugin.add_list_item(data, is_folder=False))
        return items


    def action_browse_show(self):
        url = self.base_url + 'VideoLibraryContents.aspx?GetChildOnly=true&PanelID=2&ShowID=%s' % (self.args['show_id'],)
        soup = BeautifulSoup(self.plugin.fetch(url, max_age=self.cache_timeout))
        div = soup.find('div',{'id': re.compile('^Level\d$')})
        levelclass = [c for c in re.split(r"\s+", div['class']) if c.startswith("Level")][0]
        levelclass = int(levelclass[5:])
        items = []
        if levelclass == 4:
            # Sites like TSN Always return level4 after the top level
            for li in soup.findAll('li'):
                a = li.find('dl', {"class": "Item"}).dt.a
                data = {}
                data.update(self.args)
                data.update(parse_bad_json(a['onclick'][45:-16]))
                data['action'] = 'play_clip'
                data['clip_id'] = data['ClipId']
                items.append(self.plugin.add_list_item(data, is_folder=False))
        else:
            for li in soup.find('ul').findAll('li'):
                a = li.find('a')
                is_folder = True
                data = {}
                data.update(self.args)
                if "Interface.GetChildPanel('Season'" in a['onclick']:
                    data['action'] = 'browse_season'
                    data['season_id'] = a['id']
                elif "Interface.GetChildPanel('Episode'" in a['onclick']:
                    data['action'] = 'browse_episode'
                    if self.plugin.get_setting("make_playlists") == "true":
                        data['action'] = 'play_episode'
                        data['station'] = self.long_name
                    data['episode_id'] = a['id'][8:]
                data['Title'] = decode_htmlentities(a['title'])
                items.append(self.plugin.add_list_item(data))
        return items

    def clipid_to_stream_url(self, clipid):
        rurl = "http://cls.ctvdigital.net/cliplookup.aspx?id=%s" % (clipid)
        parse = URLParser(swf_url=self.swf_url)
        url = parse(self.plugin.fetch(rurl).read().strip()[17:].split("'",1)[0])
        return url

    def action_play_clip(self):
        url = self.clipid_to_stream_url(self.args['clip_id'])
        logging.debug("Playing Stream: %s" % (url,))
        return self.plugin.set_stream_url(url)


class Fashion(BellMediaOldBaseChannel):
    short_name = 'fashion'
    base_url = 'http://watch.fashiontelevision.com/AJAX/'
    long_name = 'Fashion Television'
    swf_url = 'http://watch.fashiontelevision.com/Flash/player.swf?themeURL=http://watch.fashiontelevision.com/themes/FashionTelevision/player/theme.aspx'


class OldDiscoveryBaseChannel(BellMediaOldBaseChannel):
    status = STATUS_GOOD
    is_abstract = True
    base_url = 'http://watch.discoverychannel.ca/AJAX/'
    root_url = 'FeaturedFrame.aspx'
    default_action = 'root'
    swf_url = "http://watch.discoverychannel.ca/Flash/player.swf?themeURL=http://watch.discoverychannel.ca/themes/Discoverynew/player/theme.aspx"

    def action_root(self):
        url = self.base_url + self.root_url + self.bin_id
        soup = BeautifulSoup(self.plugin.fetch(url, max_age=self.cache_timeout))
        ul = soup.find('div', {'class': 'Frame'}).find('ul')
        items = []
        for li in ul.findAll('li'):
            data = {}
            data.update(self.args)
            data['Title'] = decode_htmlentities(li.a['title'])
            data['Plot'] = li.find('dd', {'class':'Description'}).text
            data['action'] = 'browse_show'
            onclick = li.a['onclick']
            m = re.search(r'.*\((\d+)\s\)', onclick)
            if not m:
                continue
            data['show_id'] = m.group(1)
            items.append(self.plugin.add_list_item(data))
        return items

    def action_browse_show(self):
        url = self.base_url + 'ClipLookup.aspx?episodeid=%s' % self.args['show_id']
        fu = self.plugin.fetch(url, max_age=self.cache_timeout)
        text = fu.read()
        fu.close()
        arrayitems = re.findall(r'videoArray.push\(\s*new Video\(\s*({.*?})\s*\)\s*\);', text)
        segments = [ yaml.load(item.replace(":'", ": '")\
                                   .replace(":false", ": false"))
                     for item in arrayitems ]

        items = []
        clips = [ item['ClipId'] for item in segments ]
        data = {}
        data.update(self.args)
        data['action'] = 'play_segments'
        data['Thumb'] = segments[0]['EpisodeThumbnail']
        data['segments'] = ",".join(clips)
        items.append(self.plugin.add_list_item(data, is_folder=False))

        return items

    def action_play_segments(self):
        segments = []
        for segment in self.args['segments'].split(","):
            url = self.clipid_to_stream_url(segment)
            segments.append(self.plugin.set_stream_url(url))
        data = { 'label' : 'segments', 'segments' : segments }
        return data

class AnimalPlanet(OldDiscoveryBaseChannel):
    short_name = 'animalplanet'
    long_name = 'Animal Planet'
    bin_id = '?BinId=8621'

class DiscoveryWorld(OldDiscoveryBaseChannel):
    short_name = 'discoveryworld'
    long_name = 'Discovery World'
    bin_id = '?BinId=8622'

class DiscoveryScience(OldDiscoveryBaseChannel):
    short_name = 'discoveryscience'
    long_name = 'Discovery Science'
    bin_id = '?BinId=8623'

class InvestigationDiscovery(OldDiscoveryBaseChannel):
    short_name = 'investigationdiscovery'
    long_name = 'Investigation Discovery'
    bin_id = '?BinId=8624'

