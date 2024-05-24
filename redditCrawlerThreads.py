import requests 
import requests.auth
import json
import pprint
import pymongo
import datetime
import time
import random
import threading

mongoClient = pymongo.MongoClient("localhost", 27017)  #mongodb://128.226.29.112:27017
db = mongoClient['redditTest'] #create database

headers = {
    'user-agent': 'ohboyisurehopethisworks'
}

VERBOSE = False

#Formats json, needs to be first due to .json and ? char
firstParam = ".json?raw_json=1"
#requires an int when using, ex: limit=5
limitParam = "&limit="
#after and before params are mutually exclusive 
afterParam = "&after"
beforeParam = "&before"
depthParam = "&depth="
countParam = "&count="

BASE_API_URL = "https://reddit.com/r/"

threads = []

#data needs to be json/dict object
def prettyPrint(data):
    return pprint.pformat(data, compact=True, indent=3).replace("'",'"')

class Client:
 
    #subreddit should be a string of the subreddit
    #returns a response object that represents a json, gets "amount" of posts from /new
    #Or returns None on request error
    def getNewCatalogue(self, subreddit, amount):
        try:
            catalogue = requests.get(BASE_API_URL+subreddit+"/new"+firstParam
            +limitParam+str(amount), headers=headers)
            return catalogue
        except:
            return None
    
    def getBestCatalogue(self, subreddit, amount):
        try:
            catalogue = requests.get(BASE_API_URL+subreddit+"/best"+firstParam
            +limitParam+str(amount), headers=headers)
            return catalogue
        except:
            return None
    
    def getHotCatalogue(self, subreddit, amount):
        try:
            catalogue = requests.get(BASE_API_URL+subreddit+"/hot"+firstParam
            +limitParam+str(amount), headers=headers)
            return catalogue
        except:
            return None

    def getComments(self, subreddit, id):
        try:
            comments = requests.get(BASE_API_URL+subreddit+"/comments/"+id+firstParam, headers=headers)
            return comments
        except:
            return None

    def getSubComments(self, subreddit, amt):
        try:
            comments = requests.get(BASE_API_URL+subreddit+"/comments/"+firstParam+limitParam+str(amt), headers=headers)
            return comments
        except: return None
    
def MHSCheck(comment):
    CONF_THRESHOLD = 0.9
    data = {
        "token": "3b7124c687d7492cb4ae0788a7eff0bf",
        "text": comment
    }
    attempts = 0
    while True:
        try:
            response = requests.post("https://api.moderatehatespeech.com/api/v1/moderate/", json=data).json()
        except Exception as e:
            if VERBOSE:
                print("Comment: ", comment[:10])
                print("Error: ", e)
            if attempts >= 3: return None
            attempts += 1
            continue 
        break
    if ("response" not in response.keys()) or (response["response"] != "Success"): return None
    retDict = {
        "hateFlag" : True,
        "confidence" : response["confidence"]
    }
    if response["class"] == "flag" and float(response["confidence"]) > CONF_THRESHOLD:
        return retDict
    retDict["hateFlag"] = False
    return retDict

def buildPostDict(post):
    postID = post['data']['id']
    userID = post['data']['author_fullname'][3:]
    postTimestamp = post['data']['created_utc']
    subreddit = post['data']['subreddit']
    title = post['data']['title']
    body = post['data']['selftext']
    retDict = {
        'postID' : postID,
        'userID' : userID,
        'timestamp' : datetime.datetime.fromtimestamp(postTimestamp),
        'subreddit' : subreddit,
        'title' : title,
        'body' : body,
        'MHS' : MHSCheck(body),
        'comments' : []
        }
    return retDict

def buildCommentDict(comment):
    try:
        body = comment['data']['body']
        if (body == "[removed]") or (body == "[deleted]"): return None
        postID = comment['data']['id']
        userID = comment['data']['author_fullname'][3:]
        commentTimestamp = comment['data']['created_utc']
        subreddit = comment['data']['subreddit']
        retDict = {
            'postID' : postID,
            'userID' : userID,
            'timestamp' : datetime.datetime.fromtimestamp(commentTimestamp),
            'subreddit' : subreddit,
            'body' : body,
            'MHS' : MHSCheck(body)
            }
        return retDict
    except Exception as e: 
        return None

s = open("subreddits.txt", "r").read().split(",")

subReddits = list(map(lambda x: (x, db.items), s[:-1]))
subReddits.append((s[-1], db.polItems))

client = Client()

def postThread(i, newCat, dbCollection):
    time.sleep(1)
    post = buildPostDict(newCat['data']['children'][i])
    pID = post['postID']
    if not dbCollection.find_one({'postID' : pID}):
        dbCollection.insert_one(post)

def commentThread(c, dbCollection):
    time.sleep(1)
    comEntry = buildCommentDict(c)
    if VERBOSE:
        print("\n---NEW COMMENT---\n")
        print(comEntry)
        print("\n------\n")
    if (comEntry != None):
        pID = c['data']['link_id'][3:]
        if dbCollection.find_one({'postID' : pID}):
            oldEntry = dbCollection.find_one({'postID' : pID})
            oldComList = oldEntry['comments']
            if VERBOSE:
                print("\n---OLD LIST---\n")
                print(oldComList, pID)
                print("\n------\n")
            if oldComList == None:
                oldComList = []
                oldComList.append(comEntry)
            elif (comEntry not in oldComList):
                oldComList.append(comEntry)
                
            if VERBOSE:
                print("\n---UPDATED LIST---\n")
                print(oldComList, pID)
                print("\n------\n")
            dbCollection.update_one({'postID' : pID}, {"$set" : {"comments": oldComList}})

# just default gets the last 25 newest posts
def getData(r, dbCollection):
    time.sleep(1)
    if VERBOSE: print("ENTERING THREAD\n")
    newCat = client.getNewCatalogue(r, 25).json()
    while ((newCat == None) or ("error" in newCat.keys())):
        sleepInterval = random.randint(10, 30)
        time.sleep(sleepInterval)
        newCat = client.getNewCatalogue(r, 25).json()
    for i in range(0, 25):
        t = threading.Thread(target=postThread, daemon=False, args=(i, newCat, dbCollection))
        t.start()
        threads.append(t)
    #get 25 newest comments
    newComs = client.getSubComments(r, 25).json()
    while((newComs == None) or ("error" in newComs.keys())):
        sleepInterval = random.randint(10, 30)
        time.sleep(sleepInterval)
        newComs = client.getSubComments(r, 25).json()
    for c in newComs['data']['children']:
        t = threading.Thread(target=commentThread, daemon=False, args=(c, dbCollection))
        t.start()
        threads.append(t)
    if VERBOSE: print("ENDING THREAD\n")

#entry point
baseTCount = threading.active_count()
for r, dbCollection in subReddits:
    t = threading.Thread(target=getData, daemon=False, args=(r, dbCollection))
    t.start()
    threads.append(t)
for t in threads:
    t.join()
    



