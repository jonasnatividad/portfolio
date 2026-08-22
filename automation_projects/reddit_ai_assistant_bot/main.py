from dotenv import load_dotenv
import logging
import os
import praw

#Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(filename='bot_log.log', level=logging.INFO, format='%(asctime)s:%(levelname)s:%(message)s')

reddit = praw.Reddit(
    client_id=os.environ.get("REDDIT_CLIENT_ID"),
    client_secret=os.environ.get("REDDIT_CLIENT_SECRET"),
    user_agent=os.environ.get("REDDIT_USER_AGENT"),
    username=os.environ.get("REDDIT_USERNAME"),
    password=os.environ.get("REDDIT_PASSWORD")
)

subreddit = reddit.subreddit("StardewValley")

question_keywords = ['?', 'Help', 'help', 'What', "What's", 'what', 'How', "How's", 'how', 'Where', "Where's", 'When', "When's", 'when', 'Why', "Why's", 'why', 'Trying', 'trying', "Can't", "can't"]
matched_posts = 0

for submission in subreddit.new(limit=10):
    try:
        title = submission.title.lower()
        if any(keyword.lower() in title for keyword in question_keywords):
            submission.reply("I like to use this AI assistant for quick answers to anything Stardew related: https://chat.openai.com/g/g-DiXWrwbgA-stardew-guru. It's powered by the official Stardew Valley Wiki and has saved me so much time.")
            matched_posts += 1
            logging.info(f'Replied to post: {submission.title} (ID: {submission.id})')
    except Exception as e:
        logging.error(f'Error in processing submission {submission.id}: {e}')

if matched_posts == 0:
    logging.info("No posts with the specified question keywords were found within the limit of 10 posts.")
