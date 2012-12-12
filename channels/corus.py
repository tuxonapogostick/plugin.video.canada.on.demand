from brightcove import BrightcoveBaseChannel
from utils import *
import json
import logging

class TreehouseTV(BrightcoveBaseChannel):

    short_name = 'treehouse'
    long_name = 'Treehouse TV'
    default_action = 'root'
    base_url = 'http://media.treehousetv.com'

    # dynamically load this, default id:
    player_id = 904944191001

    publisher_id = 694915333001
    flash_experience_id="myExperience"

    def action_root(self):
        # JSON data, but missing fields: url = "http://media.treehousetv.com/videos.ashx?c="
        soup = BeautifulSoup(self.plugin.fetch(self.base_url + "/", max_age=self.cache_timeout))

        player_id = None
        try:
            player_id = soup.find('object').find("param", {"name": "playerId"})['value']
        except:
            pass

        level0 = soup.find("ul", {"class": "level_0"})

        # Find all the categories but filter out the 'Full Episodes' group
        links = level0.findAll('a', {"class": "category-link", 'href':
            lambda a: "t=full+episodes" not in a})
        for link in links:
            data = {}
            data.update(self.args)
            data['Title'] = link.text
            data['action'] = 'list_episodes'
            data['query'] = link['href']
            data['player_id'] = player_id
            self.plugin.add_list_item(data)

        self.plugin.end_list()

    def action_list_episodes(self):
        query = self.args.get('query')

        data = self.plugin.fetch(self.base_url + "/videos.ashx" + query,
                max_age=self.cache_timeout).read()
        logging.debug(data)
        jdata = json.loads(data)

        for episode in jdata:
            data = {}
            data.update(self.args)
            data['Title'] = episode['Name']
            data['Plot'] = episode['ShortDescription']
            data['Thumb'] = episode['ThumbnailURL']
#            data['Duration'] = episode['Duration']

            data['action'] = 'play_video'
            data['showid'] = episode['Id']
            self.plugin.add_list_item(data, is_folder=False)
        self.plugin.end_list('episodes')

    def action_play_video(self):
        showid = self.args.get('showid')
        player_id = self.args.get('player_id')

        if not player_id:
            player_id = self.player_id

        info = self.get_clip_info(player_id, showid, self.publisher_id)
        self.video_id = showid
        self.get_swf_url()
        logging.debug(self.swf_url)
        parser = URLParser(swf_url=self.swf_url, swf_verify=True)
        url = self.choose_rendition(info['renditions'])['defaultURL']

        app, playpath = url.split("&")
        qs = "?videoId=%s&lineUpId=&pubId=%s&playerId=%s&affiliateId=" % (self.video_id, self.publisher_id, player_id)
        scheme,netloc = app.split("://")

        netloc, app = netloc.split("/",1)
        app = app.rstrip("/") + qs
        logging.debug("APP:%s" %(app,))
        tcurl = "%s://%s:1935/%s" % (scheme, netloc, app)
        logging.debug("TCURL:%s" % (tcurl,))
        url = "%s app=%s playpath=%s swfUrl=%s swfVfy=true pageUrl=%s" %(tcurl, app, playpath,
                self.swf_url, "http://media.treehousetv.com")
        self.plugin.set_stream_url(url)
