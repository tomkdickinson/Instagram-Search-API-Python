import json
import logging as log
import re
import sys
from abc import ABCMeta, abstractmethod
from json import JSONDecodeError

import bs4
import requests


class InstagramUser:
    def __init__(self, user_id, username=None, bio=None, followers_count=None, following_count=None, is_private=False):
        """
        A class to represent an Instagram User

        :param user_id: User ID of instagram user
        :param username: Username of Instagram user
        :param bio: Bio text for user
        :param followers_count: Number of followers
        :param following_count: Number of people following
        :param is_private: Boolean to indicate if account is private or not
        """
        self.id = user_id
        self.username = username
        self.bio = bio
        self.followers_count = followers_count
        self.following_count = following_count
        self.is_private = is_private


class InstagramPost:
    def __init__(self, post_id, code, user=None, caption="", display_src=None, is_video=False, created_at=None):
        """
        A class to represent a post on Instagram
        :param post_id: ID of the post
        :param code: Code of the post
        :param user: A user object representing the owner of the post
        :param caption: The caption/text of the post
        :param display_src: The URL of the image of the post
        :param is_video: A boolean value indicating it's a video
        :param created_at: The time it was created
        """
        self.post_id = post_id
        self.code = code
        self.caption = caption
        self.user = user
        self.display_src = display_src
        self.is_video = is_video
        self.created_at = created_at

    def processed_text(self):
        """
        Processes a caption to remove newlines in it.
        :return:
        """
        if self.caption is None:
            return ""
        else:
            text = re.sub('[\n\r]', ' ', self.caption)
            return text

    def hashtags(self):
        """
        Simple hashtag extractor to return the hastags in the post
        :return:
        """
        hashtags = []
        if self.caption is None:
            return hashtags
        else:
            for tag in re.findall("#[a-zA-Z0-9]+", self.caption):
                hashtags.append(tag)
            return hashtags


class HashTagSearch(metaclass=ABCMeta):
    instagram_root = "https://www.instagram.com"

    def __init__(self, ):
        """
        This class performs a search on Instagrams hashtag search engine, and extracts posts for that given hashtag.

        There are some limitations, as this does not extract all occurrences of the hash tag.

        Instead, it extracts the most recent uses of the tag.
        """
        super().__init__()

    def extract_recent_tag(self, tag):
        """
        Extracts Instagram posts for a given hashtag
        :param tag: Hashtag to extract
        """

        url_string = "https://www.instagram.com/explore/tags/%s/" % tag
        response = bs4.BeautifulSoup(requests.get(url_string).text, "html.parser")
        potential_query_ids = self.get_query_id(response)
        shared_data = self.extract_shared_data(response)

        media = shared_data['entry_data']['TagPage'][0]['graphql']['hashtag']['edge_hashtag_to_media']['edges']

        posts = []
        for node in media:
            post = self.extract_recent_instagram_post(node['node'])
            posts.append(post)
        self.save_results(posts)

        end_cursor = shared_data['entry_data']['TagPage'][0]['graphql']['hashtag']['edge_hashtag_to_media']['page_info']['end_cursor']

        # figure out valid queryId
        success = False
        print(potential_query_ids)
        for potential_id in potential_query_ids:
            variables = {
                'tag_name': tag,
                'first': 4,
                'after': end_cursor
            }
            url = "https://www.instagram.com/graphql/query/?query_hash=%s&variables=%s" % (potential_id, json.dumps(variables))
            try:
                data = requests.get(url).json()
                if data['status'] == 'fail':
                    # empty response, skip
                    continue
                query_id = potential_id
                success = True
                break
            except JSONDecodeError as de:
                # no valid JSON retured, most likely wrong query_id resulting in 'Oops, an error occurred.'
                pass
        if not success:
            log.error("Error extracting Query Id, exiting")
            sys.exit(1)

        while end_cursor is not None:
            url = "https://www.instagram.com/graphql/query/?query_hash=%s&tag_name=%s&first=12&after=%s" % (
                query_id, tag, end_cursor)
            data = json.loads(requests.get(url).text)
            end_cursor = data['data']['hashtag']['edge_hashtag_to_media']['page_info']['end_cursor']
            posts = []
            for node in data['data']['hashtag']['edge_hashtag_to_media']['edges']:
                posts.append(self.extract_recent_query_instagram_post(node['node']))
            self.save_results(posts)

    @staticmethod
    def extract_shared_data(doc):
        for script_tag in doc.find_all("script"):
            if script_tag.text.startswith("window._sharedData ="):
                shared_data = re.sub("^window\._sharedData = ", "", script_tag.text)
                shared_data = re.sub(";$", "", shared_data)
                shared_data = json.loads(shared_data)
                return shared_data

    @staticmethod
    def extract_recent_instagram_post(node):
        return InstagramPost(
            post_id=node['id'],
            code=node['shortcode'],
            user=InstagramUser(user_id=node['owner']['id']),
            caption=HashTagSearch.extract_caption(node),
            display_src=node['display_url'],
            is_video=node['is_video'],
            created_at=node['taken_at_timestamp']
        )

    @staticmethod
    def extract_recent_query_instagram_post(node):
        return InstagramPost(
            post_id=node['id'],
            code=node['shortcode'],
            user=InstagramUser(user_id=node['owner']['id']),
            caption=HashTagSearch.extract_caption(node),
            display_src=node['display_url'],
            is_video=node['is_video'],
            created_at=node['taken_at_timestamp']
        )

    @staticmethod
    def extract_caption(node):
        if len(node['edge_media_to_caption']['edges']) > 0:
            return node['edge_media_to_caption']['edges'][0]['node']['text']
        else:
            return None

    @staticmethod
    def extract_owner_details(owner):
        """
        Extracts the details of a user object.
        :param owner: Instagrams JSON user object
        :return: An Instagram User object
        """
        username = None
        if "username" in owner:
            username = owner["username"]
        is_private = False
        if "is_private" in owner:
            is_private = is_private
        user = InstagramUser(owner['id'], username=username, is_private=is_private)
        return user

    def get_query_id(self, doc):
        query_ids = []
        for script in doc.find_all("script"):
            if script.has_attr("src"):
                text = requests.get("%s%s" % (self.instagram_root, script['src'])).text
                if "queryId" in text:
                    for query_id in re.findall("(?<=queryId:\")[0-9A-Za-z]+", text):
                        query_ids.append(query_id)
        print(query_ids)
        return query_ids

    @abstractmethod
    def save_results(self, instagram_results):
        """
        Implement yourself to work out what to do with each extract batch of posts
        :param instagram_results: A list of Instagram Posts
        """


class HashTagSearchExample(HashTagSearch):
    def __init__(self):
        super().__init__()
        self.total_posts = 0

    def save_results(self, instagram_results):
        super().save_results(instagram_results)
        for i, post in enumerate(instagram_results):
            self.total_posts += 1
            print("%i - %s" % (self.total_posts, post.processed_text()))


if __name__ == '__main__':
    log.basicConfig(level=log.INFO)
    HashTagSearchExample().extract_recent_tag("christmas")
