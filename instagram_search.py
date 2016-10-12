import json
import requests
import re
import logging as log
from abc import ABCMeta, abstractmethod


class InstagramUser:

    def __init__(self, user_id, username=None, bio=None, followers_count=None, following_count=None, is_private=False):
        self.id = user_id
        self.username = username
        self.bio = bio
        self.followers_count = followers_count
        self.following_count = following_count
        self.is_private = is_private


class InstagramPost:

    def __init__(self, post_id, code, user=None, caption="", display_src=None, is_video=False, created_at=None):
        self.post_id = post_id
        self.code = code
        self.caption = caption
        self.user = user
        self.display_src = display_src
        self.is_video = is_video
        self.created_at = created_at

    def processed_text(self):
        if self.caption is None:
            return ""
        else:
            text = re.sub('[\n\r]', ' ', self.caption)
            return text

    def hashtags(self):
        hashtags = []
        if self.caption is None:
            return hashtags
        else:
            for tag in re.findall("#[a-zA-Z0-9]+", self.caption):
                hashtags.append(tag)
            return hashtags


class ExtractInstagram(metaclass=ABCMeta):

    def __init__(self, request_timeout=10000, error_timeout=10000, request_retries=3):
        super().__init__()
        self.request_timeout = request_timeout
        self.error_timeout = error_timeout
        self.request_retries = request_retries
        self.instagram_root = "https://www.instagram.com"
        self.csrf_token, self.cookie_string = self.get_csrf_and_cookie_string()
        log.info("CSRF Token set to %s", self.csrf_token)
        log.info("Cookie String set to %s" % self.cookie_string)

    def extract_recent_tag(self, tag):
        """
        Extracts Instagram posts for a given hashtag
        :param tag:
        :return:
        """

        url_string = "https://www.instagram.com/explore/tags/%s/?__a=1" % tag
        response = requests.get(url_string).text
        result = json.loads(response)
        nodes = result["tag"]["media"]["nodes"]
        cursor = result['tag']['media']['page_info']['end_cursor']
        last_cursor = None
        while len(nodes) != 0 and cursor != last_cursor:
            instagram_posts = self.extract_instagram_posts(nodes)
            self.save_results(instagram_posts)
            last_cursor = cursor
            nodes, cursor = self.get_next_results(tag, cursor)

    def get_csrf_and_cookie_string(self):
        """
        This method connects to Instagram, and returns a list of headers we need in order to process further
        requests
        :return: A header parameter list
        """
        resp = requests.head(self.instagram_root)

        return resp.cookies['csrftoken'], resp.headers['set-cookie']

    def get_next_results(self, tag, cursor):
        log.info("Getting %s with cursor %s" % (tag, cursor))
        nodes = []
        next_cursor = cursor
        post_data = self.get_query_param(tag, cursor)
        headers = self.get_headers("https://www.instagram.com/explore/tags/%s/" % tag)
        try:
            request_json = \
                json.loads(requests.post("https://www.instagram.com/query/", data=post_data, headers=headers).text)
            if "media" in request_json and "nodes" in request_json["media"]:
                nodes = request_json["media"]["nodes"]
                if "page_info" in request_json["media"]:
                    next_cursor = request_json["media"]["page_info"]["end_cursor"]
        except Exception as e:
            log.error(e)
        return nodes, next_cursor

    def extract_instagram_posts(self, nodes):
        posts = []
        for node in nodes:
            user = self.extract_owner_details(node["owner"])

            # Extract post details
            text = None
            if "caption" in node:
                text = node["caption"]
            post = InstagramPost(node['id'], node['code'], user=user, caption=text, display_src=node["display_src"],
                                 created_at=node["date"], is_video=node["is_video"])
            posts.append(post)
        return posts

    @staticmethod
    def extract_owner_details(owner):
        username = None
        if "username" in owner:
            username = owner["username"]
        is_private = False
        if "is_private" in owner:
            is_private = is_private
        user = InstagramUser(owner['id'], username=username, is_private=is_private)
        return user

    def get_headers(self, referrer):
        return {
            "referer": referrer,
            "accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-GB,en;q=0.8,en-US;q=0.6",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "cookie": self.cookie_string,
            "origin": "https://www.instagram.com",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/49.0.2623.87 Safari/537.36",
            "x-csrftoken": self.csrf_token,
            "x-instagram-ajax": "1",
            "X-Requested-With": "XMLHttpRequest"
        }

    @staticmethod
    def get_query_param(tag, end_cursor):
        """
        Returns the query params required to load next page on Instagram
        :param tag:
        :param end_cursor:
        :return:
        """
        return {
            'q':
                "ig_hashtag(%s) { media.after(%s, 100) {" % (tag, end_cursor) +
                "  count," +
                "  nodes {" +
                "    caption," +
                "    code," +
                "    date," +
                "    dimensions {" +
                "      height," +
                "      width" +
                "    }," +
                "    display_src," +
                "    id," +
                "    is_video," +
                "    likes {" +
                "      count," +
                "      nodes {" +
                "        user {" +
                "          id," +
                "          username," +
                "          is_private" +
                "        }" +
                "      }" +
                "    }," +
                "    comments {" +
                "      count" +
                "    }," +
                "    owner {" +
                "      id," +
                "      username," +
                "      is_private" +
                "    }," +
                "    thumbnail_src" +
                "  }," +
                "  page_info" +
                "}" +
                " }",
            "ref": "tags::show"}

    @abstractmethod
    def save_results(self, instagram_results):
        """
        Implement yourself to work out what to do with each extract batch of posts
        :param instagram_results:
        :return:
        """


class ExtractInstagramExample(ExtractInstagram):

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
    ExtractInstagramExample().extract_recent_tag("brexit")
