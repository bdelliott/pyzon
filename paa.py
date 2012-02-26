# http://aws.amazon.com/archives/Product-Advertising-API/4044124515194371

import base64
import hashlib
import hmac
import logging
logger = logging.getLogger("amazon")
logger.setLevel(logging.INFO)

from optparse import OptionParser
import sys
import time
import urllib
from xml.etree import ElementTree as ET

import net

ASSOCIATE_TAG = "<your associate tag>"
AWS_KEY = "<your aws key>"
AWS_SECRET = "<your aws secret>"

class Product(object):
    ''' individual product result information '''
    
    def __init__(self):
        self.asin = None
        self.detail_url = None
        self.category = None   # e.x. Book, DVD, Apparel, Toy, Movie
        self.title = None       # product title
        
        self.author = None      # author, probably only available for books.
        self.actors = []        # actor(s), probably only available for movies/tv shows/etc
        self.artists = []       # artist(s), probably only available for music
        
        self.lowest_new_price = None       # new lowest price, as a float 
        
        self.small_image_url = None
        self.medium_image_url = None
        self.large_image_url = None
        
        self.sales_rank = None
        
    def __str__(self):
        return "ASIN %s %s\t%s (#%s)" % (self.asin, self.category, self.title.encode("ascii", "ignore"), self.sales_rank)
  

class ItemLookupResponse(object):
    ''' item lookup response information encapsulated here. '''
    def __init__(self):
        self.request_id = None
        self.is_valid = False
        self.product = None
        
    def __str__(self):
        return "Request id: %s, valid: %d, product %s" % (self.request_id, self.is_valid, self.product.asin)


class ItemSearchResponse(object):
    ''' item search response information encapsulated here. '''
    def __init__(self):
        self.request_id = None
        self.is_valid = False
        self.num_results = 0
        self.num_pages = 0
        self.products = []
        
    def __str__(self):
        return "Request id: %s, valid: %d, num_results: %d, pages: %d" % (self.request_id, self.is_valid, 
                    self.num_results, self.num_pages)
        
class BrowseNode(object):
    ''' info for a single browse node. '''
    
    def __init__(self):
        self.node_id = -1
        self.name = None
        self.category_root = None
        
    def __str__(self):
        if self.category_root:
            root = str(self.category_root)
        else:
            root = "Unknown"
        
        return "%s (%d) (root: %s)" % (self.name, self.node_id, root)
        
        
class BrowseNodeLookupResponse(object):
    ''' browse node lookup response encapsulated here. '''
    
    def __init__(self):
        self.request_id = None
        self.is_valid = False

        self.node = None
        self.children = []  # immediate children
        self.ancestors = [] # immediate ancestors
        
    def dump(self):
        ''' print it '''
        
        print self.node
        sys.stdout.write("  Ancestors:")
        for a in self.ancestors:
            sys.stdout.write("\n    ")
            sys.stdout.write(str(a))
        print ""
        sys.stdout.write("  Children:")
        for c in self.children:
            sys.stdout.write("\n    ")
            sys.stdout.write(str(c))
        print ""
        
class ProductAdvertisingAPI(object):

    locale = {
        "US": "ecs.amazonaws.com",
    }
    
    def __init__(self, aws_key=None, aws_secret=None, associate_tag=None, locale="US", api_version="2011-08-01", printurl=False):
        
        if aws_key is None:
            self.aws_key = AWS_KEY
        else:
            self.aws_key = aws_key
            
        if aws_secret is None:
            self.aws_secret = AWS_SECRET
        else:
            self.aws_secret = aws_secret
            
        if associate_tag is None:
            self.associate_tag = ASSOCIATE_TAG
        else:
            self.associate_tag = associate_tag
            
        self.locale_host = self.locale[locale]
        self.printurl = printurl

        self.locale_url = "http://%s/onca/xml" % self.locale_host
        
        self.api_version = api_version
        self.xmlns = "http://webservices.amazon.com/AWSECommerceService/%s" % self.api_version
        

    def browse_node_lookup(self, browse_node_id, response_group="BrowseNodeInfo"):
        ''' Perform a BrowseNodeLookup operation 
        
            Top-level browse nodes are documented here: http://docs.amazonwebservices.com/AWSECommerceService/latest/DG/index.html?BrowseNodeIDs.html
        '''
        
        response = BrowseNodeLookupResponse()
        
        etree = self.fetchxml("BrowseNodeLookup", BrowseNodeId=str(browse_node_id), ResponseGroup=response_group)
                              
        # convert element tree to an ItemSearchResponse object
        root = etree.getroot()
        
        xpath = "%s/%s" % (self.qname("OperationRequest"), self.qname("RequestId"))
        request_id = root.find(xpath)
        response.request_id = request_id.text    # Amazon's unique id for this request.  (probably handy for tracking.)
        
        xpath = str(self.qname("BrowseNodes"))
        browse_nodes = root.find(xpath)

        xpath = "%s/%s" % (self.qname("Request"), self.qname("IsValid"))
        isvalid = browse_nodes.find(xpath)
        response.is_valid = self.str2bool(isvalid.text)

        xpath = str(self.qname("BrowseNode"))
        browse_node = browse_nodes.find(xpath)
        
        def parse_browse_node(element):
            xpath = str(self.qname("BrowseNodeId"))
            node_id = element.find(xpath)
            node_id = int(node_id.text)
        
            xpath = str(self.qname("Name"))
            name = element.find(xpath)
            name = name.text
        
            xpath = str(self.qname("IsCategoryRoot"))
            category_root = element.find(xpath)
            if category_root is not None:
                category_root = self.str2bool(category_root.text)
                
            node = BrowseNode()
            node.node_id = node_id
            node.name = name
            node.category_root = category_root
            return node
            

        response.node = parse_browse_node(browse_node)
        
        # do ancestors list, ignore ancestors of ancestors:
        xpath = str(self.qname("Ancestors"))
        ancestors = browse_node.find(xpath)
        
        if ancestors is not None:
            # top nodes have no ancestors.
            for bn in ancestors:
                node = parse_browse_node(bn)
                response.ancestors.append(node)
            
        # do children list:
        xpath = str(self.qname("Children"))
        children = browse_node.find(xpath)
        
        for bn in children:
            node = parse_browse_node(bn)
            response.children.append(node)


        return response
        
    def convert_item_lookup_response(self, root):
        ''' scrape the interesting bits out of an element tree item lookup response.  return an ItemLookupResponse object '''
        
        response = ItemLookupResponse()

        xpath = "%s/%s" % (self.qname("OperationRequest"), self.qname("RequestId"))
        request_id = root.find(xpath)
        response.request_id = request_id.text    # Amazon's unique id for this request.  (probably handy for tracking.)
            
        #logger.info("Amazon request id: %s" % request_id)
        
        xpath = str(self.qname("Items"))
        items = root.find(xpath)
        
        xpath = "%s/%s" % (self.qname("Request"), self.qname("IsValid"))
        isvalid = items.find(xpath)
        response.is_valid = self.str2bool(isvalid.text)
        
        if not response.is_valid:
            raise Exception("Request not valid!")

        xpath = str(self.qname("Items"))
        items = root.find(xpath)
        
        # "Items" part of the document seems exactly the same as in Item Search responses:
        products = self.convert_items(items)
        
        # should be 1 product in the response
        if len(products) != 1:
            raise Exception("ItemLookup returned unexpected number of products (%d).  Expected 1" % len(products))
        
        response.product = products[0]
        
        return response
        
    def convert_item_search_response(self, root):
        ''' scrape the interesting bits out of an element tree item search response.  return an ItemSearchResponse object '''

        response = ItemSearchResponse()
        
        xpath = "%s/%s" % (self.qname("OperationRequest"), self.qname("RequestId"))
        request_id = root.find(xpath)
        
        response.request_id = request_id.text    # Amazon's unique id for this request.  (probably handy for tracking.)
            
        #logger.info("Amazon request id: %s" % request_id)
        
        xpath = str(self.qname("Items"))
        items = root.find(xpath)
        
        xpath = "%s/%s" % (self.qname("Request"), self.qname("IsValid"))
        isvalid = items.find(xpath)
        response.is_valid = self.str2bool(isvalid.text)
        
        if not response.is_valid:
            raise Exception("Request not valid!")
        
        xpath = str(self.qname("TotalResults"))
        num_results = items.find(xpath)
        response.num_results = int(num_results.text)
        
        xpath = str(self.qname("TotalPages"))
        num_pages = items.find(xpath)
        response.num_pages = int(num_pages.text)

        # process list of items
        products = self.convert_items(items)
        response.products = products
        
        return response
        
    def convert_items(self, items):
        ''' Process a list of items from an ItemLookup or ItemSearch response.  return a list of Product objects '''
        
        products = []
        
        xpath = str(self.qname("Item"))
        item_list = items.findall(xpath)
        for item in item_list:
            product = Product()
            
            # NOTE: all 'text' strings in the parsed XML that need to be utf-8 decode are already unicode strings because python tries to be super smart about which type
            # of string to construct.  Do no further utf-8 decoding here!
            
            xpath = str(self.qname("ASIN"))
            product.asin = item.find(xpath).text

            xpath = str(self.qname("DetailPageURL"))
            product.detail_url = item.find(xpath).text
        
            xpath = str(self.qname("SalesRank"))
            rank = item.find(xpath)
            if rank is not None:
                product.sales_rank = rank.text

            # stuff like actor, product group, etc is in the item attributes block
            xpath = str(self.qname("ItemAttributes"))
            item_attributes = item.find(xpath)
            
            # check for 1 or more actors:
            xpath = str(self.qname("Actor"))
            actors = item_attributes.findall(xpath)
            for a in actors:
                product.actors.append(a.text)

            # check for 1 or more artists:
            xpath = str(self.qname("Artist"))
            artists = item_attributes.findall(xpath)
            for a in artists:
                product.artists.append(a.text)
                
            # mp3 downloads appear to have a Creator field instead of an artist.  if we didn't find an artist, check for creator:
            if len(product.artists) == 0:
                xpath = str(self.qname("Creator"))
                creator = item_attributes.find(xpath)
                if creator is not None:
                    product.artists.append(creator.text)
            
            xpath = str(self.qname("ProductGroup"))
            product.category = item_attributes.find(xpath).text
            
            xpath = str(self.qname("Title"))
            product.title = item_attributes.find(xpath).text
            
            # i think this is only available for books:
            xpath = str(self.qname("Author"))
            auth = item_attributes.find(xpath)
            if auth is not None:
                product.author = auth.text

            # get pricing information from OfferSummary group:
            xpath = str(self.qname("OfferSummary"))
            offer_summary = item.find(xpath)
            
            # no offer summary response group for Kindle books (others too, perhaps?)
            if offer_summary is None:
                logger.info("No offer summary for ASIN %s (%s)" % (product.asin, product.title))
            else:
                xpath = str(self.qname("LowestNewPrice"))
                lowest_new_price = offer_summary.find(xpath)
                
                if lowest_new_price is None:
                    logger.info("No lowest new price for ASIN %s (%s)" % (product.asin, product.title))
                else:
                    xpath = str(self.qname("Amount"))
                    amt = lowest_new_price.find(xpath)
                   
                    if amt is None:
                        logger.info("Lowest new price has NO Amount field for asin %s" % product.asin)
                        
                    else:
                        # the Amount field is given as "1699", meaning $16.99
                        product.lowest_new_price = int(amt.text) / 100.0
            
            # some item results do not have small/med/large images.  (they may have ImageSets)
            xpath = "%s/%s" % (self.qname("SmallImage"), self.qname("URL"))
            image = item.find(xpath)
            if image is not None:
                product.small_image_url = image.text

            xpath = "%s/%s" % (self.qname("MediumImage"), self.qname("URL"))
            image = item.find(xpath)
            if image is not None:
                product.medium_image_url = image.text

            xpath = "%s/%s" % (self.qname("LargeImage"), self.qname("URL"))
            image = item.find(xpath)
            if image is not None:
                product.large_image_url = image.text

            logger.info(product)

            products.append(product)
            
        logger.info("Converted %d items to products" % len(products))
        return products

        
    def construct_url(self, operation, operation_params):
        ''' construct aws url '''
        
        # need a sorted list of all request parameters so we can generate a signature.
        params = [
            "Service=AWSECommerceService",
            "Operation=" + operation,
            "AWSAccessKeyId=" + self.aws_key,
        ]
        
        if self.associate_tag:
            params.append("AssociateTag=" + self.associate_tag)
        
        for (operation_param, operation_value) in operation_params.items():
            
            if operation_value is not None:
                p = "%s=%s" % (operation_param, urllib.quote(operation_value))
                params.append(p)


        params.append("Version=" + self.api_version)

        # just for debug, generate "unsigned url" to test with their signature helper:
        # http://associates-amazon.s3.amazonaws.com/signed-requests/helper/index.html
        #print self.locale_url + "?" + "&".join(params)
        
        timestamp = self.timestamp()
        params.append("Timestamp=" + urllib.quote(timestamp))

        # sort by byte value - not alphabetical
        params = sorted(params)
        
        # join params by ampersand (&) for signing:
        param_string = "&".join(params)
        
        # generate hmac signature:
        signature = self.sign(param_string)
        param_string += "&Signature=" + signature
        
        url = self.locale_url + "?" + param_string
        return url

    def fetch(self, operation, operation_params):
        ''' fetch document, return file-like object as response '''
        
        url = self.construct_url(operation, operation_params)
        
        if self.printurl:
            logger.info(url)

        # Google App Engine supports Python 2.7 as of release 1.6.0.  However, there is an outstanding bug (#6271) in their standard library facade over the urlfetch
        # service, so use urlfetch directly if we're on GAE.
        f = net.get(url)
        return f
        
    def fetchxml(self, operation, **operation_params):
        ''' return document as an ElementTree '''
        
        f = self.fetch(operation, operation_params)
        
        # be very careful when parsing elements to preserve their unicode-ness
        etree = ET.parse(f)
        return etree
        
    def sign(self, param_string):
        ''' Calculate an RFC 2104-compliant HMAC with the SHA256 hash algorithm
            (as per http://docs.amazonwebservices.com/AWSECommerceService/2010-11-01/DG/)
        '''
        
        # prepend some magic poop:
        s = "GET\n%s\n/onca/xml\n%s" % (self.locale_host, param_string)
        
        signature = self.sign_with_key(self.aws_secret, s)
        return signature
        
    def sign_with_key(self, key, msg):
        
        # and the voodoo:
        h = hmac.new(key, msg, hashlib.sha256)
        signature = base64.b64encode(h.digest())    # base-64-ify it

        # urlencode it:
        signature = urllib.quote(signature)
        
        return signature
        
    def str2bool(self, s):
        ''' string to boolean '''
        return s in ["True", "true"]
        
    def timestamp(self):
        ''' Format required timestamp in GMT time
            ex: Timestamp=2009-01-01T12:00:00Z '''
            
        t = time.gmtime() # time tuple in gmt zone
        return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", t)

    def item_lookup(self, asin, response_group="Medium"):
        ''' Do amazon item lookup operation '''
        
        etree = self.fetchxml("ItemLookup", ItemId=asin, Condition="All", ResponseGroup=response_group)
        
        # convert element tree to an ItemSearchResponse object
        root = etree.getroot()
        return self.convert_item_lookup_response(root)
        

    def item_search(self, keywords=None, browse_node=None, search_index="All", response_group="Medium", title=None):
        ''' Medium response group provides basic information and also gives includes the URLs for product images. '''
        
        # search across all indices for available items.  
        
        etree = self.fetchxml("ItemSearch", BrowseNode=browse_node, SearchIndex=search_index, Condition="All", 
                              ResponseGroup=response_group, Keywords=keywords, Title=title)
                              
        # convert element tree to an ItemSearchResponse object
        root = etree.getroot()
        return self.convert_item_search_response(root)

        
    def item_search_async_google(self, keywords, search_index="All", response_group="Medium", page=1, deadline=5):
        ''' Start an asynchronous request with Google App Engine's urlfetch service.
        
            deadline - Optional parameter to control request timeout.  (in seconds)
         '''
        
        operation_params = {
            "SearchIndex" : search_index,
            "ItemPage" : str(page),
            "ResponseGroup" : response_group,
            "Keywords" : keywords
        }
        url = self.construct_url("ItemSearch", operation_params)
        
        if self.printurl:
            logger.info(url)

        from google.appengine.api import urlfetch
        rpc = urlfetch.create_rpc(deadline=deadline, callback=None)
        
        urlfetch.make_fetch_call(rpc, url, method="GET")

        
        return rpc
        
        
    def qname(self, element_name):
        return ET.QName(self.xmlns, element_name)
        
        
    def xml_string_to_item_search_response(self, xml):
        ''' Take a full ItemSearchResponse XML document as a string and convert it to a usable object '''    
        
        root = ET.fromstring(xml) # returns the root element as an element tree Element object.
        return self.convert_item_search_response(root)
        
    
if __name__=='__main__':
    logging.basicConfig()
    
    parser = OptionParser()
    parser.add_option("-u", "--printurl", dest="printurl", help="Print AWS request URL", metavar="PRINTURL", 
                      default=False, action="store_true")
    (options, args) = parser.parse_args()
                      
    api = ProductAdvertisingAPI(AWS_KEY, AWS_SECRET, printurl=options.printurl)
    
    #response = api.item_search("a few good men")
    #response = api.item_search(args[0])

    #response = api.item_search(title="bitch came back*", search_index="MP3Downloads")
    #logger.info("Item search response: %s" % response)
    
    # 17 = Literature & Fiction
    #browse_node_id = int(args[0])
    #print "node: %d" % browse_node_id
    #response = api.browse_node_lookup(browse_node_id)
    #response.dump()
    
    #asin = "B002WY65VU" # zombieland dvd
    #response = api.item_lookup(asin)
    #logger.info("Item lookup response: %s" % response)


    api.item_search(keywords="stumbling*", browse_node="283155", search_index="Books", response_group="Medium")
    #logger.info("Item search response: %s" % response)
