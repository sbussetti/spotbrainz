#!/usr/bin/env python

"""
spotbrainz
"""

CLIENT_ID = 'REDACTED'
CLIENT_SECRET = 'REDACTED'
REDIRECT_URI = 'http://localhost/spotbrainz'
SCOPE = (
    'playlist-read-private',
    'playlist-modify-private',
    'user-top-read',
    'user-read-recently-played',
    'user-library-read'
)
USER_ID = 'REDACTED'

def main(user_id):
    """
    main
    """
    token = spotipy.util.prompt_for_user_token(
        user_id,
        ' '.join(SCOPE),
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI
    )

    if token:
        spot = Spot(token, user_id, trace=False)
        # spot.purge_db()
        # spot.fetch()
        # spot.display_table('tracks', order_by='created, played_at')
        # spot.display_table('albums', order_by='created')
        # spot.display_table('artists', order_by='created')
        # spot.display_table('_default')
        spot.update_recommendations()
        spot.db_info()
    else:
        print("Can't get token for", user_id)

if __name__ == '__main__':

    from spot import Spot
    import spotipy.util

    main(USER_ID)
