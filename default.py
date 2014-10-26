#! /usr/bin/python
# vim:ts=4:sw=4:ai:et:si:sts=4:fileencoding=utf-8

import os, sys
import shutil
import sha
import cgi
#import xbmc, xbmcaddon, xbmcgui, xbmcplugin
import logging
logging.basicConfig(level=logging.WARNING)
import urllib, urllib2, urlparse
import time
from utils import urldecode
from channels import *
from channel import *
import socket
socket.setdefaulttimeout(50)
from ConfigParser import SafeConfigParser
import json
import StringIO

#try:
#    from sqlite3 import dbapi2 as sqlite
#except:
#    from pysqlite2 import dbapi2 as sqlite

__plugin__ = "Canada On Demand"
__author__ = 'Andre,Renaud  {andrepleblanc,renaudtrudel}@gmail.com'
__url__ = 'http://xbmcaddons.com/addons/plugin.video.canada.on.demand/'
__date__ = '05-03-2014'
__version__ = '0.8.6'
#__settings__ = xbmcaddon.Addon(id='plugin.video.canada.on.demand')

BASEDIR = "/opt/prf/persist/canada"
CACHEDIR = BASEDIR + "/cache"
CONFIGDIR = BASEDIR + "/config"
CONFIGFILE = CONFIGDIR + "/plugin.conf"
CODEDIR = "/opt/prf/src/plugin.video.canada.on.demand"
RESOURCEDIR = CODEDIR + "/resources"

logger = logging.getLogger(__name__)

config = SafeConfigParser()
try:
	config.readfp(open(CONFIGFILE))
except Exception, e:
    logger.error("Error: %s" % e)

class OnDemandPlugin(object):

    def _urlopen(self, url, retry_limit=4, browser=None, user_agent=None):
        retries = 0
        while retries < retry_limit:
            logger.debug("fetching %s" % (url,))
            if browser:
                try:
                    browser.get(url)
                    return StringIO.StringIO(browser.page_source)
                except Exception:
                    retries += 1
            else:
                # Add referer for CTV to work properly
                url_scheme, netloc, path, query, fragment = urlparse.urlsplit(url)
                req = urllib2.Request(url)
                req.add_header("Referer", "%s://%s/" % (url_scheme, netloc))
                if user_agent:
                    req.add_header("User-Agent", user_agent)

                try:
                    return urllib2.urlopen(req)
                except (urllib2.HTTPError, urllib2.URLError), e:
                    retries += 1
            raise Exception("Failed to retrieve page: %s" %(url,))

    def _urlretrieve(self, url, filename, retry_limit=4, browser=None,
                     user_agent=None):
        inf = self._urlopen(url, retry_limit, browser, user_agent)
        with open(filename, "w") as f:
            return f.write(inf.read())
        inf.close()

    def fetch(self, url, max_age=None, browser=None, user_agent=None):
        if max_age is None:
            return self._urlopen(url, browser=browser, user_agent=user_agent)

        tmpurl = url
        scheme, tmpurl = tmpurl.split("://",1)
        netloc, path = tmpurl.split("/",1)
        fname = sha.new(path).hexdigest()
        _dir = fname[:4]
        cacheroot = self.get_cache_dir()
        cachepath = os.path.join(cacheroot, netloc, _dir)
        if not os.path.exists(cachepath):
            os.makedirs(cachepath)

        download = True
        cfname = os.path.join(cachepath, fname)
        if os.path.exists(cfname):
            ctime = os.path.getctime(cfname)
            if time.time() - ctime < max_age:
                download = False

        if download:
            logger.debug("Fetching: %s" % (url,))
            if browser:
                browser.get(url)
                with open(cfname, "w") as f:
                    f.write(browser.page_source.encode('utf-8'))
            else:
                self._urlretrieve(url, cfname, browser=browser,
                                  user_agent=user_agent)
        else:
            logger.debug("Using Cached: %s" % (url,))

        return open(cfname)



    def get_url(self,urldata):
        """
        Constructs a URL back into the plugin with the specified arguments.

        """
        return "%s?%s" % (self.script_url, urllib.urlencode(urldata,1))

    def action_channel_list(self):
        """
        List all registered Channels

        Channels are automatically registered simply by being imported
        and being subclasses of BaseChannel.

        """
        items = []
        for channel_code, channel_class in sorted(ChannelMetaClass.registry.channels.iteritems()):
            info = channel_class.get_channel_entry_info()

            # Default to <short_name>.png if no icon is set.
            if info['Thumb'] is None:
                info['Thumb'] = info['channel'] + ".png"

            try:
                info['Thumb'] = self.get_resource_path('images','channels', info['Thumb'])
            except ChannelException:
                logger.warn("Couldn't Find Channel Icon for %s" % (channel_code,))

            items.append(self.add_list_item(info))
        return items

    def set_stream_url(self, url, info=None, type="rtmp"):
        """
        Resolve a Stream URL and return it to XBMC.

        'info' is used to construct the 'now playing' information
        via add_list_item.

        """
        listitem = { 'label' : 'clip', 'path' : url,
                     'proxyhost' : self.proxy,
                     'httpproxyport' : self.proxy_port,
                     'type' : type }
        return listitem

    def get_cache_dir(self):
        """
        return an acceptable cache directory.

        """
        # I have no idea if this is right.
        path = CACHEDIR
        if not os.path.exists(path):
            os.makedirs(path)
        return path


    def get_setting(self, id, section="general"):
        """
        return a user-modifiable plugin setting.

        """
        try:
            return config.get(section, id)
        except Exception:
            return None


    def add_list_item(self, info, is_folder=True, return_only=False,
                      context_menu_items=None, clear_context_menu=False, bookmark_parent=None, bookmark_id=None, bookmark_folder_id=None):
        """
        Creates an XBMC ListItem from the data contained in the info dict.

        if is_folder is True (The default) the item is a regular folder item

        if is_folder is False, the item will be considered playable by xbmc
        and is expected to return a call to set_stream_url to begin playback.

        if return_only is True, the item item isn't added to the xbmc screen but
        is returned instead.


        Note: This function does some renaming of specific keys in the info dict.
        you'll have to read the source to see what is expected of a listitem, but in
        general you want to pass in self.args + a new 'action' and a new 'remote_url'
        'Title' is also required, anything *should* be optional

        """
        if context_menu_items is None:
            context_menu_items = []

        info.setdefault('Thumb', '')
        info.setdefault('Icon', info['Thumb'])
        if 'Rating' in info:
            del info['Rating']

        li = { 'label' : info['Title'], 'iconImage' : info['Icon'],
               'thumbnailImage' : info['Thumb'] }

        if not is_folder:
            li['IsPlayable'] = True
            context_menu_items.append(("Queue Item", "Action(Queue)"))

        li['videoInfo'] = { k : unicode(v) for k, v in info.iteritems() }

        # Add Context Menu Items
        if context_menu_items:
            li['contextMenuItems'] = context_menu_items

        li['url'] = self.get_url(info)

        return li

    def get_resource_path(self, *path):
        """
        Returns a full path to a plugin resource.

        eg. self.get_resource_path("images", "some_image.png")

        """
        p = os.path.join(RESOURCEDIR, *path)
        #p = os.path.join(__settings__.getAddonInfo('path'), 'resources', *path)
        if os.path.exists(p):
            return p
        raise ChannelException("Couldn't Find Resource: %s" % (p, ))

    def action_plugin_root(self):
        items = []
        items.append(self.add_list_item({
            'Title': 'All Channels',
            'action': 'channel_list',
            'Thumb': os.path.join(CODEDIR, 'icon.png')
        }))
        return items

    def __call__(self):
        """
        This is the main entry point of the plugin.
        the querystring has already been parsed into self.args

        """

        action = self.args.get('action', None)

        if not action:
            action = 'plugin_root'

        if hasattr(self, 'action_%s' % (action,)):
            func = getattr(self, 'action_%s' % (action,))
            return func()

        # If there is an action, then there should also be a channel
        channel_code = self.args.get('channel', None)

        # The meta class has a registry of all concrete Channel subclasses
        # so we look up the appropriate one here.

        channel_class = ChannelMetaClass.registry.channels[channel_code]
        chan = channel_class(self, **self.args)

        return chan()

    def check_cache(self):
        cachedir = self.get_cache_dir()
        version_file = os.path.join(cachedir, __version__)
        if not os.path.exists(version_file):
            shutil.rmtree(cachedir)
            os.mkdir(cachedir)
            with open(version_file, 'w') as f:
                f.write("\n")

    def __init__(self, script_url, handle, querystring):
        self.json_outfile = handle
        self.proxy = self.get_setting("http_proxy")
        self.proxy_port = self.get_setting("http_proxy_port")
        self.service_args = None
        if self.proxy and self.proxy_port:
            proxy_handler = urllib2.ProxyHandler({'http':'%s:%s'%(self.proxy,self.proxy_port)})
            opener = urllib2.build_opener(proxy_handler)
            urllib2.install_opener(opener)
            self.service_args = [ '--proxy=%s:%s' % (self.proxy, self.proxy_port) ]

        self.script_url = script_url
        self.handle = 1 # int(handle)
        if len(querystring) > 2:
            self.querystring = querystring[1:]
            items = urldecode(self.querystring)
            self.args = dict(items)
        else:
            self.querystring = querystring
            self.args = {}
#        self.connect_to_db()
        self.check_cache()
        self.browser = None
        logger.debug("Constructed Plugin %s" % (self.__dict__,))

def recursiveGet(parent, url):
    url = url.replace(sys.argv[0], "")
    plugin = OnDemandPlugin(sys.argv[0], sys.argv[1], url)
    try:
        results = plugin()
    except Exception as e:
        results = []
    for result in results:
        if type(result) is dict:
            print result['label']
            if not 'IsPlayable' in result and 'url' in result:
                recursiveGet(result, result['url'])

    if parent:
        if not 'children' in parent:
            parent['children'] = []
        parent['children'].append(results)
    else:
        return results

def grabAllJson(results):
    for result in results:
        label = result['label']
        print label
        if label.lower() == 'cbc':
            url = result['url'].replace(sys.argv[0], "")
            plugin = OnDemandPlugin(sys.argv[0], sys.argv[1], url)
            cbcresults = plugin()
            for cbcresult in cbcresults:
                cbclabel = cbcresult['label']
                print cbclabel
                chanresults = recursiveGet(None, cbcresult['url'])
                with open('out/all-' + cbclabel + '.json', "w") as f:
                    f.write(json.dumps(chanresults, sort_keys=True,
                                       indent=4, separators=(',', ': ')))

            continue

        if not 'url' in result:
            continue
        chanresults = recursiveGet(None, result['url'])
        with open('out/all-' + label + '.json', "w") as f:
            f.write(json.dumps(chanresults, sort_keys=True,
                               indent=4, separators=(',', ': ')))

if __name__ == '__main__':
    json_outfile = sys.argv[1]
    plugin = OnDemandPlugin(*sys.argv)
    results = plugin()
    # grabAllJson(results)
    if not results:
        results = []
    print results
    with open(json_outfile, "w") as f:
        f.write(json.dumps(results))
