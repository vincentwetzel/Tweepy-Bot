# TODO: make better docs throughout

import discord
import pandas
from discord.ext import commands
import asyncio

import tweepy

import json
import os

from typing import List

import logging
from datetime import datetime

logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

# Initialize Bot settings
description = '''This is Vincent's Twitter Bot. Use the !command syntax to send a command to the bot.'''
bot = commands.Bot(command_prefix='!', description=description)

ADMIN_DISCORD_ID = None

tracked_ids: List[str] = list()
tracked_accounts: List[str] = list()


@bot.event
async def on_ready():
    await log_msg_to_server_owner(await pad_message("Tweepy Bot is now online!") + "\n", False)

    asyncio.create_task(init_Tweepy())


async def init_Tweepy() -> None:
    """
    TODO: Doc this
    :param loop:
    :return:
    """
    # Init tokens
    with open("tweepy_tokens.ini", 'r') as f:
        consumer_key = ""
        consumer_secret = ""
        access_token = ""
        access_token_secret = ""

        lines = f.readlines()

        for line in lines:
            if "consumer_key=" in line:
                consumer_key = line.split("consumer_key=")[1].strip()
            elif "consumer_secret=" in line:
                consumer_secret = line.split("consumer_secret=")[1].strip()
            elif "access_token=" in line:
                access_token = line.split("access_token=")[1].strip()
            elif "access_token_secret=" in line:
                access_token_secret = line.split("access_token_secret=")[1].strip()
            else:
                raise Exception("The settings failed to initiate from the settings file.")

    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_token_secret)
    tweepy_api = tweepy.API(auth, wait_on_rate_limit=True, wait_on_rate_limit_notify=True)

    # initialize streams
    xlsx = pandas.ExcelFile("Twitter_Accounts.xlsx")
    changed = False
    data_frames: List[pandas.DataFrame] = list()
    for sheet_name in xlsx.sheet_names:
        df: pandas.DataFrame = pandas.read_excel(xlsx, sheet_name, usecols=["Account", "Twitter_ID"])
        df.name = sheet_name
        data_frames.append(df)
        for idx, row in df.iterrows():
            if pandas.isnull(row["Twitter_ID"]) or (type(row["Twitter_ID"]) == str and not row["Twitter_ID"].isdigit()):
                # Excel file contains a blank Twitter_ID OR a misformatted Twitter_ID
                val = tweepy_api.get_user(screen_name=row["Account"]).id
                df.loc[idx, "Twitter_ID"] = val
                changed = True

    if changed:
        with pandas.ExcelWriter("Twitter_Accounts.xlsx", engine="xlsxwriter") as writer:
            for df in data_frames:
                df.to_excel(writer, df.name, index=False)
            writer.save()

    global tracked_ids
    global tracked_accounts

    for df in data_frames:
        # await (await get_text_channel(bot.get_guild(429002252473204736), df.name)).send(
        #    await pad_message("Initializing Tweepy streams for: " + df.name))
        for idx, row in df.iterrows():
            tracked_accounts.append(row["Account"])
            tracked_ids.append(int(row["Twitter_ID"]))
        # await asyncio.sleep(900)
    await init_tweepy_streams(tweepy_api, tracked_ids, "twitter", True)
    await (await get_text_channel(bot.get_guild(429002252473204736), "twitter")).send(
        await pad_message("Tweepy initialization complete!"))

    await log_msg_to_server_owner("Tweepy has been fully initialized!")


async def init_tweepy_streams(tweepy_api: tweepy.API, twitter_id_list: List[int], message_channel_name: str,
                              skip_retweets: bool) -> None:
    """
    Initializes a Tweepy stream.
    :param tweepy_api: The Tweepy API in use
    :param twitter_id_list: A list of Twitter IDs
    :param message_channel_name: The channel to message when any of these Users tweet.
    :param skip_retweets: Whether or not retweets/mentions should be documented.
    :return: None
    """
    message_channel = await get_text_channel(bot.get_guild(429002252473204736), message_channel_name)
    stream_listener = TweepyStreamListener(discord_message_method=message_channel.send,
                                           async_loop=asyncio.get_event_loop(), skip_retweets=skip_retweets)

    stream = tweepy.Stream(auth=tweepy_api.auth, listener=stream_listener, tweet_mode='extended')
    stream.filter(follow=[str(x) for x in twitter_id_list], is_async=True, stall_warnings=True)


async def get_text_channel(guild: discord.Guild, channel_name: str) -> discord.TextChannel:
    """
    Gets the text channel requested, creates if the channel does not exist.
    :param guild: The Guild for this request
    :param channel_name: The channel to be fetched or created
    :return: The Text Channel object
    """
    # Find the channel if it exists
    for channel in list(guild.text_channels):
        if channel.name == channel_name:
            return channel

    # If no Text Channel with this name exists, create one.
    return await guild.create_text_channel(channel_name, reason="Text Channel was requested but did not exist.")


async def log_msg_to_server_owner(msg: str, add_time_and_date: bool = True, tts_param=False):
    """
    Sends a DM to the bot's owner.
    :param msg: The message to send
    :param add_time_and_date: Prepend information about the date and time of the logging item
    :param tts_param: Text-to-speech option
    :return:
    """
    msg = await add_time_and_date_to_string(msg) if (add_time_and_date is True) else msg
    await (await bot.fetch_user(ADMIN_DISCORD_ID)).send(msg, tts=tts_param)


async def add_time_and_date_to_string(msg):
    return datetime.now().strftime("%m-%d-%y") + "\t" + datetime.now().strftime("%I:%M:%S%p") + "\t" + msg


def init_bot_token(token_file: str) -> str:
    """
    Gets the bot's token from a file
    :param token_file: The token file from which to get the bot's token number.
    :return: The bot's token as a string.
    """
    if not os.path.exists(token_file):
        with open(token_file, 'a') as f:  # 'a' opens for appending without truncating
            token = input("The token file does not exist. Please enter the bot's token: ")
            f.write(token)
    else:
        with open(token_file, 'r+') as f:  # 'r+' is reading/writing mode, stream positioned at start of file
            token = f.readline().rstrip('\n')  # readline() usually has a \n at the end of it
            if not token:
                token = input("The token file is empty. Please enter the bot's token: ")
                f.write(token)
    return token


def init_admin_discord_id(id_fname: str) -> int:
    """
    Initializes the owner ID so the bot knows who is in charge.
    :param id_fname: The name of the file that contains the admin's id number
    :return: The ID of the admin user as a string.
    """
    if os.path.isfile("admin_dicord_id.txt"):
        with open("admin_dicord_id.txt", 'r') as f:
            try:
                line = f.readline().strip()
                if line and len(line) == 18:  # Discord IDs are 18 characters.
                    try:
                        return int(line)
                    except ValueError as e:
                        print(e)
                        print("There was an issue with the discord ID found in " + id_fname
                              + ". This file should only contain an 18-digit number and nothing else")
            except EOFError as e:
                print(e)
                print(id_fname + " is empty. This file must contain the user ID of the bot's admin")
    with open("admin_dicord_id.txt", "w") as f:
        id = input("Please enter the Discord ID number for the admin you want this bot to report to: ")
        f.write(id)
        return id


async def pad_message(msg, add_time_and_date=True, dash_count=75) -> str:
    """
    Pads a message with stars
    :param msg: The message
    :param add_time_and_date: Adds time and date
    :param dash_count: The number of stars to use in the padding
    :return: A new string with the original message padded with stars.
    """
    if add_time_and_date:
        msg = "\n" + (await add_time_and_date_to_string(msg)) + "\n"
    else:
        msg = "\n" + msg + "\n"
    # dash_count = len(log_msg) - 2
    for x in range(dash_count):
        msg = "-".join(["", msg, ""])
    return msg


def pp_jsonn(json_thing, sort=True, indents=4):
    if type(json_thing) is str:
        print(json.dumps(json.loads(json_thing), sort_keys=sort, indent=indents))
    else:
        print(json.dumps(json_thing, sort_keys=sort, indent=indents))
    return None


class TweepyStreamListener(tweepy.StreamListener):
    def __init__(self, discord_message_method, async_loop, skip_retweets=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.discord_message_method = discord_message_method
        self.async_loop = async_loop
        self.skip_retweets = skip_retweets

    def on_status(self, status: tweepy.Status) -> None:
        """
        # Executes when a new status is Tweeted.
        :param status: The status
        :return: None
        """

        # Only log tweets authored or retweeted by the tracked User.
        if status.user.screen_name in tracked_accounts:
            self.send_message("https://twitter.com/" + status.user.screen_name + "/status/" + str(status.id))
        else:
            return

    def on_exception(self, exception):
        print("on_exception has caught the following exception:" + str(exception))
        return

    def on_error(self, status_code) -> None:
        """
        Tweepy error handling method
        :param status_code: The Twitter error code (not an HTTP code)
        :return: None
        """
        future = asyncio.run_coroutine_threadsafe(
            self.discord_message_method("Error Code (" + str(status_code) + ")"), self.async_loop)
        future.result()

    def send_message(self, msg) -> None:
        """
        # Sends a message
        :param msg:
        :return:
        """
        # Submit the coroutine to a given loop
        future = asyncio.run_coroutine_threadsafe(self.discord_message_method(msg), self.async_loop)
        # Wait for the result with an optional timeout argument
        future.result()


if __name__ == "__main__":
    try:
        ADMIN_DISCORD_ID = int(init_admin_discord_id("admin_discord_id.txt"))
    except TypeError as e:
        print(e)
        print("This error means that there is something wrong with your admin_discord_id.txt file.")

    bot.run(init_bot_token("discord_token.txt"))
