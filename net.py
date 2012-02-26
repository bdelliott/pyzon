from cStringIO import StringIO 
import logging
logger = logging.getLogger("amazon")
import urllib
import urllib2

''' App engine is wonky with respect to using urllib2.  Sometimes perfectly valid URLs raise a 404 if urllib2 is used.  So.  Try to detect if we're on app engine and use its urlfetch api directly if we are...

'''

try:
    from google.appengine.api import urlfetch
    app_engine = True
except ImportError:
    # not on app engine.
    app_engine = False
    
    
def app_engine_get(url):
    ''' do a HTTP get using app engine's urlfetch interface directly '''
    
    try:
        response = urlfetch.fetch(url, method="GET", deadline=10) # 10 second deadline
        if not response.status_code == 200:
            raise Exception("Failed to get %s via urlfetch.  HTTP status code was %d" % (url, response.status_code))
            
        return response.content
        
    except:
        logger.error("Failed to GET %s via urlfetch" % url)
        raise
        

def standard_lib_get(url):
    ''' do an HTTP get using python's urllib2 package '''

    try:
        result = urllib2.urlopen(url)
        return result.read()

    except urllib2.URLError, e:
        logger.error("Failed to get %s via urllib2" % url)
        raise

    
def get(url):
    ''' do a simple synchronous get request for this URL '''
    
    #logger.debug("GET %s" % url)
    
    
    if app_engine:
        s = app_engine_get(url)
    else:
        s = standard_lib_get(url)
        
    # Still a string of bytes, not *decoded* into utf-8 yet, though all amazon responses should be utf-8 judging by the Content-Type response header.
    # Be Verrrrrrry careful with unicode handling.
    
    # turn response string into a file-like object:
    f = StringIO(s)
    return f
    
        
