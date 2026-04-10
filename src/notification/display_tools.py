import re

import aiohttp
import discord
from bs4 import BeautifulSoup
from tweety.types import Tweet

from configs.load_configs import configs


def _md_escape_label(s: str | None) -> str:
    # Minimal escaping for markdown link labels: [label](url)
    # Avoid breaking the label when it contains ']' or ')'
    if s is None:
        return ""
    return s.replace("]", "］").replace(")", "）")


def _get_media_url(media_url: str, quality: str) -> str:
    """Append Twitter image quality parameter to a media URL."""
    return f"{media_url}?name={quality}"


async def gen_embed(tweet: Tweet, quality: str = 'orig') -> list[discord.Embed]:
    author = tweet.author

    # Use tweet text as the title (the actual content), like DiscordStreamNotifyBot uses stream title
    tweet_text = tweet.text or ""
    title = tweet_text[:256] if tweet_text else f"{author.name} {get_action(tweet, disable_quoted=True)}"

    # Description: author link + open tweet link
    author_link = f"[@{_md_escape_label(author.username)}](https://twitter.com/{author.username})"
    open_tweet = f"[Open Tweet]({tweet.url})"
    description = f"{author_link} | {open_tweet}"

    embed = discord.Embed(
        title=title,
        description=description,
        url=tweet.url,
        color=0x1da0f2,
        timestamp=tweet.created_on
    )
    embed.set_author(name=f'{author.name} (@{author.username})', icon_url=author.profile_image_url_https, url=f'https://twitter.com/{author.username}')
    embed.set_thumbnail(url=re.sub(r'normal(?=\.jpg$)', '400x400', tweet.author.profile_image_url_https))

    # Action field
    action_map = {'retweeted': '🔁 轉推', 'quoted': '💬 引用推文', 'tweeted': '🐦 推文'}
    embed.add_field(name='動作', value=action_map.get(get_action(tweet), '🐦 推文'), inline=True)

    # Media field (only if media exists)
    media = tweet.media
    if media:
        if len(media) > 1:
            media_value = f'🖼️ {len(media)} 張圖片'
        elif media[0].type == 'video':
            media_value = '🎬 影片'
        elif media[0].type == 'animated_gif':
            media_value = '🎞️ GIF'
        else:
            media_value = '🖼️ 圖片'
        embed.add_field(name='媒體', value=media_value, inline=True)

    embed.set_footer(text='Twitter' if configs['embed']['built_in']['legacy_logo'] else 'X', icon_url='attachment://footer.png')

    if len(media) == 1:
        embed.set_image(url=_get_media_url(media[0].media_url_https, quality))
        return [embed]
    elif len(media) > 1:
        if configs['embed']['built_in']['fx_image']:
            async with aiohttp.ClientSession() as session:
                async with session.get(re.sub(r'twitter', r'fxtwitter', tweet.url)) as response:
                    raw = await response.text()
            fximage_url = BeautifulSoup(raw, 'html.parser').find('meta', property='og:image')['content']
            embed.set_image(url=fximage_url)
            return [embed]
        else:
            imgs_embed = [discord.Embed(url=tweet.url).set_image(url=_get_media_url(m.media_url_https, quality)) for m in media]
            imgs_embed.insert(0, embed)
            return imgs_embed
    return [embed]


def get_action(tweet: Tweet, disable_quoted: bool = False) -> str:
    if tweet.is_retweet:
        return 'retweeted'
    elif tweet.is_quoted and not disable_quoted:
        return 'quoted'
    else:
        return 'tweeted'

