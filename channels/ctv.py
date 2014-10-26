#! /usr/bin/python
# vim:ts=4:sw=4:ai:et:si:sts=4:fileencoding=utf-8
from theplatform import *
from BeautifulSoup import BeautifulStoneSoup
from selenium import webdriver
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

class CTVBaseChannel(BaseChannel):
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

    def __init__(self, plugin, **args):
        BaseChannel.__init__(self, plugin, **args)
        #self.browser = webdriver.PhantomJS(service_args=self.plugin.service_args)
    def __del__(self):
        #self.browser.close()
        pass

    def action_root(self):
        url = self.settings_js % self.brandId
        with self.plugin.fetch(url, max_age=self.cache_timeout,
                               user_agent=self.user_agend) as f:
            jsonp = f.read()
        settings = yaml.load(jsonp[jsonp.index("(") + 1 : jsonp.rindex(")")])

        items = []
        for widget in settings['widgets']:
            if widget['type'] == "collection-list":
                for item in widget['items']:
                    data = {}
                    data.update(self.args)
                    data['Title'] = item['text']
                    data['action'] = 'browse_%s' % item['collection']['type']
                    data['show_id'] = item['collection']['id']
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
                    data['show_id'] = int(m.group(1))
                    items.append(self.plugin.add_list_item(data))
        return items

    def action_browse_media(self):
        return self.action_browse_common_content(self.medias_json, 'video_id')

    def action_browse_content(self):
        return self.action_browse_common_content(self.contents_json, 'show_id')

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
                data.update(self.args)
                data['IsPlayable'] = True
                data['show_id'] = item['Id']
                data['EpisodeTitle'] = item['Name']
                data['description'] = item['Desc']
                data['action'] = 'play_episode'
                data['video_id'] = item['Media']['Id']
                data['ShowTitle'] = item['Media']['Name']
                data['Thumb'] = item['Media']['Images'][0]['Url']
                data['seasonnum'] = item['Season']['Number']
                data['episodenum'] = item['Episode']
                data['pubDate'] = item['BroadcastDate'] + " " + \
                                  item['BroadcastTime'] + " EST5EDT"
                data['content_id'] = item['ContentPackages'][0]['Id']
                data['duration'] = item['ContentPackages'][0]['Duration']
                items.append(self.plugin.add_list_item(data))

            if count <= page * 25:
                break
            page += 1

        return items

    def action_browse_media_group(self):
        baseUrl = self.media_group_json + self.json_qs
        items = []
        page = 1
        while True:
            url = baseUrl % (self.destination, int(self.args['show_id']),
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

class CTVNews(CTVBaseChannel):
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


class Bravo(CTVBaseChannel):
    short_name = 'bravo'
    long_name = 'Bravo!'
    base_url = 'http://www.bravo.ca'

    def action_root(self):
        url = self.base_url + '/Sites/Custom/Feeds/ShowList.aspx'
        soup = BeautifulSoup(self.plugin.fetch(url, max_age=self.cache_timeout)
                        , convertEntities=BeautifulStoneSoup.HTML_ENTITIES)
        shows = soup.findAll('show')

        items = []
        for show in shows:
            show_img = self.base_url + show.logo.string + 'Shows?height=103&width=183&crop=True'
            show_url = self.base_url + show.url.string

            # must check url to see if there are any videos
            soup2 = BeautifulSoup(self.plugin.fetch(show_url, max_age=self.cache_timeout))
            if not soup2.find('a', 'video_carousel_thumbnail_container'): continue

            # there are videos, so add to the list
            items.append(self.plugin.add_list_item({
                'Title': show.regex.string,
                'Thumb': show_img,
                'action': 'browse',
                'channel': self.short_name,
                'show_url': show_url
            }))
        return items
#        self.plugin.end_list('tvshows', [xbmcplugin.SORT_METHOD_LABEL])

    def action_browse(self):
        soup = BeautifulSoup(self.plugin.fetch(self.args['show_url'], max_age=self.cache_timeout))
        episodes = soup.findAll('a', 'video_carousel_thumbnail_container')

        items = []
        for ep in episodes:
            ep_img = ep.img['src']
            ep_title = ep.span.string
            ep_id = ep['href'].split('=')[1].strip()

            items.append(self.plugin.add_list_item({
                'Title': ep_title,
                'Thumb': ep_img,
                'action': 'browse_episode',
                'channel': self.short_name,
                'episode_id': ep_id
            }))
        return items
#        self.plugin.end_list('episodes', [xbmcplugin.SORT_METHOD_DATE])

    def iter_clip_list(self):
        url_template = 'http://app01.ctvdigital.com/ctvesi/datafeed/content_much.aspx?cid=%s'
        url = url_template % self.args['episode_id']
        soup = BeautifulStoneSoup(self.plugin.fetch(url, max_age=self.cache_timeout))

        clips = soup.findAll('element', vidtype='1')

        for item in clips:
            data = {}
            data.update(self.args)

            data['action'] = 'play_clip'
            data['Title'] = soup.find('headline').string
            data['Thumb'] = soup.find('image').string
            try:
                data['Title'] = item.title.string
                data['Plot'] = soup.find('subhead').string
                data['Thumb'] = soup.imageurl.string
            except: pass
            data['clip_id'] = item['id']
            yield data

    def action_play_clip(self):
        url_template = 'http://esi.ctv.ca/datafeed/urlgenjs.aspx?vid=%s'
        url = url_template % self.args['clip_id']
        logging.debug('clip url: %r' % url)

        page = self.plugin.fetch(url).read().strip()
        temp = page.split("'")[1]
        video_url = temp.split('?')[0]

        logging.debug("Playing Stream: %s" % (video_url,))
        return self.plugin.set_stream_url(video_url)


class CTV(CTVBaseChannel):
    short_name = 'ctv'
    long_name = 'CTV'
    #base_url = 'http://watch.ctv.ca/AJAX/'
    base_url = 'http://www.ctv.ca/video'
    #swf_url = 'http://watch.ctv.ca/Flash/player.swf?themeURL=http://watch.ctv.ca/themes/CTV/player/theme.aspx'
    brandId = 'ctv'
    destination = 'ctv_web'


class Discovery(CTVBaseChannel):
    short_name = 'discovery'
    base_url = 'http://watch.discoverychannel.ca/AJAX/'
    long_name = 'Discovery'
    #swf_url = 'http://watch.discoverychannel.ca/Flash/player.swf?themeURL=http://watch.discoverychannel.ca/themes/Discoverynew/player/theme.aspx'


class ComedyNetwork(CTVBaseChannel):
    status = STATUS_UGLY
    short_name = 'comedynetwork'
    base_url = 'http://watch.thecomedynetwork.ca/AJAX/'
    long_name = 'The Comedy Network'
    #swf_url = 'http://watch.thecomedynetwork.ca/Flash/player.swf?themeURL=http://watch.thecomedynetwork.ca/themes/Comedy/player/theme.aspx'



class Space(CTVBaseChannel):
    short_name = 'space'
    long_name = "Space"
    base_url = "http://watch.spacecast.com/AJAX/"
    #swf_url = "http://watch.spacecast.com/Flash/player.swf?themeURL=http://watch.spacecast.com/themes/Space/player/theme.aspx"


class BNN(CTVBaseChannel):
    base_url = 'http://watch.bnn.ca/AJAX/'
    long_name = 'Business News Network'
    short_name = 'bnn'
    #swf_url = 'http://watch.bnn.ca/news/Flash/player.swf?themeURL=http://watch.bnn.ca/themes/BusinessNews/player/theme.aspx'


class Fashion(CTVBaseChannel):
    short_name = 'fashion'
    base_url = 'http://watch.fashiontelevision.com/AJAX/'
    long_name = 'Fashion Television'
    #swf_url = 'http://watch.fashiontelevision.com/Flash/player.swf?themeURL=http://watch.fashiontelevision.com/themes/FashionTelevision/player/theme.aspx'
