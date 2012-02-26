#!/usr/bin/env python2.5
#
# use 2.5 because this will have to run on GAE.
#
# AWS product advertising API prototype
#
#

from getch import getch
import paa
import sys

CHAR_MIN = 3

def read_cmd():

    api = paa.ProductAdvertisingAPI()

    # do char by character searching 
    
    cmd = ""
    while True:
        c = getch()
        if c == "\r" or c == "\n":
            break
        sys.stdout.write(c)
        cmd += c
        
        if len(cmd) >= CHAR_MIN:
            api.item_search(cmd)
            sys.stdout.write("\n")
            

def cmdloop():
    ''' do product searches, char-by-char '''

    while True:
        sys.stdout.write(">")
        read_cmd()

if __name__=='__main__':
    
    cmdloop()
        
