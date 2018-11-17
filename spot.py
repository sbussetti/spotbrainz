"""
package spot for fetching and returning
"""
# pylint: disable=invalid-name, missing-docstring, too-many-locals

from datetime import datetime
import os
import pprint
import random
from urllib.parse import urlparse, parse_qs

from spotipy import Spotify as Spotify_
from tabulate import tabulate
from tinydb import TinyDB, Query


class Spotify(Spotify_):
    """
    Spotify
    """

    def current_user_recently_played(self, limit=50, before=None):  # pylint: disable=arguments-differ
        ''' Get the current user's recently played tracks

            Parameters:
                - limit - the number of entities to return
                - before - pagination: return items before timestamp
        '''
        return self._get('me/player/recently-played', limit=limit, before=before)


def niceo():
    """
    Nice ISO format
    """
    bits = datetime.utcnow().isoformat().split('.')
    bits[-1] = '{}Z'.format(bits[-1][0:3])
    return '.'.join(bits)


def sample(data, n=5):
    """
    pull a random sample
    """
    rsample = []

    for i, datum in enumerate(data):
        if i < n:
            rsample.append(datum)
        elif i >= n and random.random() < n/float(i+1):
            replace = random.randint(0, len(rsample)-1)
            rsample[replace] = datum
    return rsample


def blocks(seq, size):
    return (seq[pos:pos + size] for pos in range(0, len(seq), size))


class Spot():
    """
    See spot run
    """

    def __init__(self, token, user_id, trace=False):
        self.sp = Spotify(auth=token)
        self.user_id = user_id
        self.sp.trace = trace
        self.db = TinyDB('./spot.db')
        self.pprint = pprint.PrettyPrinter(indent=4).pprint
        # rows, columns =
        self.term = [int(x) for x in os.popen('stty size', 'r').read().split()]

    def purge_db(self):
        self.db.purge_tables()
        print('All tables purged')

    def db_info(self):
        Q = Query()
        tables = self.db.tables()
        print("==== TABLES ====")
        for table in tables:
            print('{}: {}'.format(table, self.db.table(table).count(Q.id)))
        print("================")

    def display_table(self, table_name, order_by=None, limit=None):
        ignore = ['is_local', 'is_playable', 'available_markets', 'disc_number',
                  'explicit', 'external_ids', 'external_urls', 'href', 'uri',
                  'linked_from', 'preview_url', 'context', 'type', 'followers',
                  'images', 'release_date', 'release_date_precision']
        table = self.db.table(table_name)
        records = table.all()
        if order_by:
            reverse = False
            if order_by.startswith('-'):
                order_by = order_by[1:]
                reverse = True
            order_by = order_by.split(',')
            records = sorted(
                records, key=lambda x: tuple(x.get(k, '') for k in order_by))
            if reverse:
                records = list(reversed(records))
        window = records[slice(0, limit)]
        if not window:
            print("No records returned")
            return
        _, columns = self.term
        fields = list(set(window[0].keys()) - set(ignore))
        # longest_field = len(sorted(fields, key=len)[-1])
        num_fields = len(fields)
        col_width = int(columns / num_fields) - 1
        # if col_width < longest_field:
        #     col_width = longest_field
        # print("COL WIDTH: {} LONGEST FIELD: {}".format(col_width, longest_field))
        rows = []
        print("================= {} ==============".format(table.name))
        for rec in window:
            rows.append({k: str(v)[0:col_width]
                         for k, v in rec.items() if k not in ignore})
        print(tabulate(rows, headers='keys'))
        print("======== Returned {} rows =========\n".format(len(window)))

    def pop_albums(self, albums):
        records = []
        Q = Query()
        albums_table = self.db.table('albums')
        for segment in blocks(albums, 20):
            album_ids = [a.get('id') for a in segment]
            for album in self.sp.albums(album_ids).get('albums', []):
                album_artists = album.pop('artists', [])
                album.update({
                    'created': niceo(),
                    'artists': [a.get('id') for a in album_artists]
                })
                records.extend(
                    albums_table.upsert(album, Q.id == album.get('id')))
        return records

    def pop_artists(self, artists):
        records = []
        Q = Query()
        artists_table = self.db.table('artists')
        for segment in blocks(artists, 50):
            artist_ids = [a.get('id') for a in segment]
            for artist in self.sp.artists(artist_ids).get('artists', []):
                artist.update({
                    'created': niceo()
                })
                records.extend(
                    artists_table.upsert(artist, Q.id == artist.get('id')))
        return records

    def fetch(self):
        """
        fetch what we need to know
        Track ->
            track ->
            played_at: <datetime>
            context: ?
        """
        next_query = {'limit': 25}
        total_tracks = 0
        total_artists = 0
        total_albums = 0
        Q = Query()
        tracks_table = self.db.table('tracks')

        # gather records
        records = []

        # all time faves
        for time_range in ['short_term', 'medium_term', 'long_term']:
            next_query = {'limit': 25, 'time_range': time_range}
            while next_query:
                resp = self.sp.current_user_top_tracks(**next_query)
                next_query = parse_qs(urlparse(resp.get('next')).query)
                if next_query:
                    self.pprint(next_query)
                records.extend(resp.get('items'))

        # recently played
        while next_query:
            resp = self.sp.current_user_recently_played(**next_query)
            next_query = parse_qs(urlparse(resp.get('next')).query)
            if next_query:
                self.pprint(next_query)
            records.extend(resp.get('items'))

        # fetch in the above order to recently played comes later,
        # preserving last play-time in the upsert

        artists = []
        albums = []
        # process records
        for item in records:
            if 'track' in item:
                # flatten other info
                track = item.pop('track')
                track.update({k: v for k, v in item.items()})
            else:
                track = item

            album = track.pop('album', None)
            if album is not None:
                artists.extend(album.get('artists', []))
                albums.append(album)

            artists.extend(track.pop('artists', []))

            track.update({
                'created': niceo(),
                'album': album.get('id') if album is not None else None,
                'artists': [a.get('id') for a in artists]
            })

            total_tracks += len(
                tracks_table.upsert(track, Q.id == track.get('id')))

        # fetch full album records for genre info
        total_albums += len(self.pop_albums(albums))

        # fetch full artists for genre info
        total_artists += len(self.pop_artists(artists))

        print(
            "Updated or created {} artists\n".format(total_artists),
            "Updated or created {} albums\n".format(total_albums),
            "Updated or created {} tracks\n".format(total_tracks),
        )

    def recommend(self):
        """
        recommendations(
            seed_artists=None,
            seed_genres=None,
            seed_tracks=None,
            limit=20,
            country=None,
            **kwargs
        )
        """
        artists = self.db.table('artists')
        albums = self.db.table('albums')
        tracks = self.db.table('tracks')
        Q = Query()

        genre_seeds = self.sp.recommendation_genre_seeds().get('genres', [])
        # artists and albums have genres .. but must be a valid seed
        seed_genres = []
        max_candidates = albums.count(Q) + artists.count(Q)
        candidates_seen = []
        # still a little leaky if there are less
        # non-unique genres than artists and albums
        while len(seed_genres) < 5 and len(candidates_seen) < max_candidates:
            genre_candidates = sample([g for subg in [
                r.get('genres', []) for r in sample(
                    sample(artists.all()) + sample(albums.all()))
            ] for g in subg])
            candidates_seen.extend(genre_candidates)
            for gc in genre_candidates:
                if gc in genre_seeds:
                    seed_genres.append(gc)
                if len(seed_genres) == 5:
                    break

        seed_artists = [a.get('id') for a in sample(artists.all())]
        seed_tracks = [a.get('id') for a in sample(tracks.all())]

        return self.sp.recommendations(
            seed_artists=seed_artists, limit=5
        ).get('tracks', []) + self.sp.recommendations(
            seed_genres=seed_genres, limit=5
        ).get('tracks', []) + self.sp.recommendations(
            seed_tracks=seed_tracks, limit=5
        ).get('tracks', [])

    def update_recommendations(self):
        Q = Query()

        # get spotbrainz playlist local meta
        pl_meta = self.db.get(Q.name == '__playlist_meta__')
        # create playlist if we don't have the id
        if not pl_meta:
            pl = self.sp.user_playlist_create(
                self.user_id, 'spotbrainz', public=False,
                description='Shoddy recommendations for spotty brains')
        else:
            pl = self.sp.user_playlist(
                self.user_id, pl_meta.get('record', {}).get('id'))
        self.db.upsert(
            {'name': '__playlist_meta__', 'record': pl},
            Q.name == '__playlist_meta__')
        pl_meta = self.db.get(Q.name == '__playlist_meta__')

        recs = self.recommend()

        self.sp.user_playlist_add_tracks(
            self.user_id,
            pl_meta.get('record', {}).get('id'),
            [r.get('uri') for r in recs]
        )
        print("*~*~*~ Updated recommended playlist ~*~*~*")
