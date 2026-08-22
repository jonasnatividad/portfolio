#!/usr/bin/env python3

import requests
from openai import OpenAI
from dotenv import load_dotenv
import os
import random
import tweepy

#Load environment variables from .env file
load_dotenv()

# OpenAI client
client = OpenAI(api_key=os.environ.get("OPEN_AI_API_KEY"))

# Random elements for the prompt
animals = [
    'lion', 'eagle', 'whale', 'kangaroo', 'tiger', 
    'elephant', 'giraffe', 'zebra', 'hippopotamus', 'rhinoceros', 
    'panda', 'gorilla', 'chimpanzee', 'orangutan', 'koala', 
    'sloth', 'wolf', 'fox', 'bear', 'deer', 
    'moose', 'elk', 'caribou', 'bison', 'antelope', 
    'cheetah', 'leopard', 'jaguar', 'lynx', 'cougar', 
    'hyena', 'meerkat', 'warthog', 'wildebeest', 'gazelle', 
    'buffalo', 'aardvark', 'porcupine', 'armadillo', 'skunk', 
    'badger', 'otter', 'beaver', 'raccoon', 'squirrel', 
    'chipmunk', 'marmot', 'prairie dog', 'capybara', 'opossum', 
    'kangaroo rat', 'hedgehog', 'platypus', 'echidna', 'wombat', 
    'tasmanian devil', 'wallaby', 'lemur', 'aye-aye', 'bushbaby', 
    'tarsier', 'marmoset', 'capuchin', 'baboon', 'mandrill', 
    'macaque', 'snow leopard', 'red panda', 'camel', 'llama', 
    'alpaca', 'vicuña', 'guanaco', 'dromedary', 'bat', 
    'flying fox', 'dolphin', 'narwhal', 'beluga', 'seal', 
    'sea lion', 'walrus', 'manatee', 'dugong', 'shark', 
    'stingray', 'octopus', 'squid', 'lobster', 'crab', 
    'sea turtle', 'jellyfish', 'starfish', 'seahorse', 'clownfish', 
    'angelfish', 'parrot', 'flamingo', 'peacock', 'penguin'
]
environments = [
    'forest', 'ocean', 'mountain', 'desert', 'jungle', 
    'savannah', 'grassland', 'tundra', 'wetland', 'marsh', 
    'swamp', 'river', 'lake', 'sea', 'reef', 
    'beach', 'island', 'volcano', 'valley', 'canyon', 
    'plain', 'plateau', 'glacier', 'ice cap', 'city', 
    'town', 'village', 'countryside', 'farm', 'garden', 
    'park', 'rainforest', 'woodland', 'meadow',
    'prairie', 'steppe', 'taiga', 'arctic', 'antarctic',
    'cave', 'underwater', 'coral reef', 'bay', 'gulf',
    'peninsula', 'archipelago', 'fjord', 'lagoon', 'delta',
    'estuary', 'cliff', 'dune', 'oasis', 'pond',
    'stream', 'brook', 'waterfall', 'hot spring', 'geyser',
    'hill', 'ridge', 'knoll', 'butte', 'mesa',
    'escarpment', 'barranca', 'basin', 'lowland',
    'upland', 'moor', 'heath', 'fen', 'bog', 
    'pampas', 'savanna', 'karst', 'badland', 'scrubland', 
    'wadi', 'fiord', 'channel', 'strait', 'sound'
]
actions = [
    'flying', 'swimming', 'running', 'jumping', 'hunting', 
    'climbing', 'diving', 'walking', 'sprinting', 'crawling', 
    'gliding', 'leaping', 'pouncing', 'grazing', 'foraging', 
    'burrowing', 'digging', 'chasing', 'fleeing', 'migrating', 
    'nesting', 'perching', 'roosting', 'singing', 'calling', 
    'dancing', 'playing', 'fighting', 'mating', 'breeding', 
    'feeding', 'resting', 'sleeping', 'sunbathing', 'camouflaging', 
    'slithering', 'scurrying', 'flapping', 'hovering', 'soaring', 
    'basking', 'hiding', 'stalking', 'ambushing', 'trapping', 
    'frolicking', 'exploring', 'wading', 'drifting', 'floating', 
    'skipping', 'rolling', 'turning', 'shaking', 'stretching', 
    'hopping', 'bouncing', 'galloping', 'trotting', 'prancing', 
    'cantering', 'charging', 'darting', 'dashing', 'skulking', 
    'lurking', 'prowling', 'roaming', 'wandering', 'traveling', 
    'navigating', 'sliding', 'glissading', 'slinking', 'sneaking', 
    'creeping', 'tiptoeing', 'lumbering', 'striding', 'strutting', 
    'parading', 'marching', 'treading', 'paddling', 'rowing', 
    'sailing', 'grooming', 'preening', 'molting', 'shedding'
]

# Randomly select elements
selected_animal_1 = random.choice(animals)
selected_animal_2 = random.choice(animals)
selected_environment = random.choice(environments)
selected_action = random.choice(actions)

# Ensure the two animals are not the same
while selected_animal_1 == selected_animal_2:
    selected_animal_2 = random.choice(animals)

# Create a unique prompt
prompt = f"Generate a creative and detailed prompt for Dall-E to create an imaginative and visually striking image of a hybrid between a {selected_animal_1} and a {selected_animal_2} in a {selected_environment} setting, performing an action of {selected_action}. The final image should only include one creature that is a displays hybrid features of each animal. Include a concise caption suitable for a Twitter post, totaling equal to or less than 185 characters total. This caption should simply describe the hybrid creature and its environment. Format the response as: Dall-E prompt: [prompt here] Caption: [caption here]."

# Generate prompt using GPT-3.5
chat_completion = client.chat.completions.create(
    messages=[
        {
            "role": "user",
            "content": prompt
        },
    ],
    model="gpt-3.5-turbo"
)

response_content = chat_completion.choices[0].message.content
print(response_content)

# Parse response to separate Dall-E prompt and caption
parts = response_content.split("Caption:")
dalle_prompt = parts[0].replace("Dall-E prompt:", "").strip()
meme_caption = parts[1].strip() if len(parts) > 1 else ""
meme_caption = meme_caption.strip("'\"")

print("Dall-E Prompt:", dalle_prompt)
print("Meme Caption:", meme_caption)

# Use the generated prompt to feed DALL-E
response = client.images.generate(
    model="dall-e-3",
    prompt=dalle_prompt,
    size="1024x1024",
    quality="standard",
    n=1,
)

# Extracting and saving the image
image_url = response.data[0].url
response = requests.get(image_url)
if response.status_code == 200:
    output_dir = "."
    filename = "ai_hybrids.jpg"

    os.makedirs(output_dir, exist_ok=True)

    with open(os.path.join(output_dir, filename), 'wb') as f:
        f.write(response.content)

    print(f"Image saved to {os.path.join(output_dir, filename)}")

# 3) Post image to twitter

api_key = os.environ.get("X_API_KEY")
api_secret = os.environ.get("X_API_SECRET_KEY")
bearer_token = os.environ.get("X_BEARER_TOKEN")
access_token = os.environ.get("X_ACCESS_TOKEN")
access_token_secret = os.environ.get("X_ACCESS_TOKEN_SECRET")

client = tweepy.Client(bearer_token, api_key, api_secret, access_token, access_token_secret)
auth = tweepy.OAuth1UserHandler(api_key, api_secret, access_token, access_token_secret)
api = tweepy.API(auth)

image_path = os.path.join(output_dir, filename)

media = api.media_upload(filename=image_path)

# Get the media ID from the response
media_id = media.media_id

# Text content of the tweet
hashtags = "#AIart #HybridAnimals #DigitalArt #CreativeAI #FantasyArt #AnimalArt #ArtOfTheDay #TechArt #AI"  
tweet_content = f"{meme_caption} {hashtags}"

print(tweet_content)

# Post the tweet with the image
client.create_tweet(text=tweet_content, media_ids=[media_id])
