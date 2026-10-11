import re

import discord
from tweety.types import Tweet

from core.classes import ParsedTweet
from configs.load_configs import configs, FX_SETTINGS
from src.i18n import t
from src.utils import escape_markdown


def _md_escape_label(s: str | None) -> str:
    # Minimal escaping for markdown link labels: [label](url)
    # Avoid breaking the label when it contains ']' or ')'
    if s is None:
        return ""
    return s.replace("]", "］").replace(")", "）")


def _get_media_url(media_url: str, quality: str) -> str:
    """Apply Twitter image quality parameter to a pbs.twimg.com media URL; leave other URLs untouched."""
    if not media_url or 'pbs.twimg.com/media/' not in media_url:
        return media_url
    return f"{media_url.split('?', 1)[0]}?name={quality}"


def gen_embed(tweet: Tweet, parsed_tweet: ParsedTweet, quality: str = 'orig') -> list[discord.Embed]:
    author = tweet.author
    disable_quoted = not FX_SETTINGS['media']['enabled']
    
    is_simplified = False
    if FX_SETTINGS['rt_text']['enabled']:
        description = (parsed_tweet.get_quote_text(simplified_content=FX_SETTINGS['rt_text']['simplified'])
                       or parsed_tweet.get_text(simplified_content=FX_SETTINGS['rt_text']['simplified'])
                       or escape_markdown(tweet.text))
        if isinstance(description, tuple):
            description, is_simplified = description[0], description[1]
    else:
        description = escape_markdown(tweet.text)

    # Title: who did what action
    title = f'{author.name} (@{_md_escape_label(author.username)}) {get_action(tweet, disable_quoted=disable_quoted)}'

    # Description: tweet text + links
    open_tweet = f'[Open Tweet]({tweet.url})'
    author_link = f'[@{_md_escape_label(author.username)}](https://twitter.com/{author.username})'
    link_line = f'{open_tweet} | {author_link}'
    description = f'{description}\n\n{link_line}' if description else link_line

    embed = discord.Embed(title=title, description=description, url=tweet.url, color=0x1da0f2, timestamp=tweet.created_on)
    embed.set_author(name=f'{author.name} (@{author.username})', icon_url=author.profile_image_url_https, url=f'https://twitter.com/{author.username}')
    embed.set_footer(text='Twitter' if configs['embed']['built_in']['legacy_logo'] else 'X', icon_url='attachment://footer.png')
    if not is_simplified:
        embed.set_thumbnail(url=re.sub(r'normal(?=\.(?:jpg|png)$)', '400x400', tweet.author.profile_image_url_https))

    # Action field
    if tweet.is_retweet:
        action_value = '🔁 轉推'
    elif tweet.is_quoted and not disable_quoted:
        action_value = '💬 引用推文'
    else:
        action_value = '🐦 推文'
    embed.add_field(name='動作', value=action_value, inline=True)

    # Media field (only if media exists)
    media = parsed_tweet.media
    if media.length > 1:
        media_value = f'🖼️ {media.length} 張圖片'
    elif media.length == 1 and media.type == 'video':
        media_value = '🎬 影片'
    elif media.length == 1 and media.type == 'animated_gif':
        media_value = '🎞️ GIF'
    elif media.length == 1:
        media_value = '🖼️ 圖片'
    else:
        media_value = None
    if media_value:
        embed.add_field(name='媒體', value=media_value, inline=True)
    
    if parsed_tweet.media.length == 1:
        embed.set_image(url=_get_media_url(parsed_tweet.media.urls[0], quality))
        return [embed]
    elif parsed_tweet.media.length > 1:
        if FX_SETTINGS['mosaic']:
            embed.set_image(url=parsed_tweet.media.mosaic_url)
            return [embed]
        else:
            imgs_embed = [discord.Embed(url=tweet.url).set_image(url=_get_media_url(url, quality)) for url in parsed_tweet.media.urls]
            imgs_embed.insert(0, embed)
            return imgs_embed
    elif FX_SETTINGS['media']['external'] and parsed_tweet.media.external_url:
        embed.set_image(url=parsed_tweet.media.external_url)
        return [embed]
    return [embed]


def get_action(tweet: Tweet, disable_quoted: bool = False) -> str:
    if tweet.is_retweet:
        return t('display.action.retweeted')
    elif tweet.is_quoted and not disable_quoted:
        return t('display.action.quoted')
    else:
        return t('display.action.tweeted')


def get_tweet_type(parsed_tweet: ParsedTweet) -> str:
    if parsed_tweet.media.length > 1:
        if getattr(parsed_tweet, 'is_mixed', False):
            return t('display.tweet_type.multi_media', count=parsed_tweet.media.length)
        return t('display.tweet_type.photos', count=parsed_tweet.media.length)
    elif parsed_tweet.media.length == 1:
        map_key = f'display.media_type_map.{parsed_tweet.media.type}'
        translated = t(map_key)
        # t() returns the key itself when the key is missing; use raw type name as fallback
        media_type = parsed_tweet.media.type if translated == map_key else translated
        return t('display.tweet_type.media', media_type=media_type)
    else:
        return t('display.tweet_type.status')
    
def get_footer_name() -> str | None:
    return None if configs['embed']['type'] == 'proxy' else ('twitter.png' if configs['embed']['built_in']['legacy_logo'] else 'x.png')
