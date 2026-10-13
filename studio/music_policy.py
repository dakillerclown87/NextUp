"""Mandatory YouTube classification policy, independent of user settings."""

YOUTUBE_MUSIC_CATEGORY = "10"
MUSIC_ONLY_ERROR = "NextUp only accepts YouTube videos labeled Music by YouTube. Choose a video in the Music category."


def require_youtube_music(category):
    if category != YOUTUBE_MUSIC_CATEGORY:
        raise ValueError(MUSIC_ONLY_ERROR)


def check_music_track(track):
    if track.get("provider") == "youtube":
        if "youtube_category_id" not in track:
            raise ValueError("This saved YouTube request has no verified Music category. Remove it and request its link again so NextUp can check it.")
        require_youtube_music(track["youtube_category_id"])
