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
                data['IsPlayable'] = True
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

class BNN(BellMediaBaseChannel):
    long_name = 'Business News Network'
    short_name = 'bnn'
    base_url = 'http://www.bnn.ca/video'
    brandId = 'bnn'
    destination = 'bnn_web'

#class Fashion(BellMediaBaseChannel):
#    short_name = 'fashion'
#    base_url = 'http://watch.fashiontelevision.com/AJAX/'
#    long_name = 'Fashion Television'
#    #swf_url = 'http://watch.fashiontelevision.com/Flash/player.swf?themeURL=http://watch.fashiontelevision.com/themes/FashionTelevision/player/theme.aspx'
