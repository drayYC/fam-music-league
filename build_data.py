#!/usr/bin/env python3
"""
Fam Music League — Data Pipeline
Processes Music League CSV exports into the data.json format expected by index.html.

Inputs (read from /mnt/user-data/uploads/):
  - rounds.csv       (round metadata)
  - competitors.csv  (player id -> full name mapping from Music League)
  - submissions.csv  (all song submissions across all rounds)
  - votes.csv        (all votes across all rounds)

Output:
  - /home/claude/data.json
"""

import csv
import json
from collections import defaultdict, Counter

UPLOAD_DIR = '/mnt/user-data/uploads'
OUTPUT_PATH = '/home/claude/data.json'

# ---------------------------------------------------------------------------
# Player map (authoritative — overrides CSV competitor names for display)
# ---------------------------------------------------------------------------
PLAYERS = {
    '0a831b84b60a4aaca7c6f3150bbccb88': 'Dray E.',
    '19e6c48a177c458398bb138a991a2e4c': 'Elyse E.',
    '2334709be13e48759338c82689b95d11': 'Gabriel M.',
    '3b87dbe243724d3bbcafea4934075fec': 'Steve E.',
    '41a0d64fae1f40489679232baec98925': 'Mary D.',
    '4853a05f049d4d4682257bed4b277eed': 'Tess D.',
    '5838e19081f440598e554c420f257ab7': 'Mills T.',
    '994734a26c814552ad88e0ce9ea4cfce': 'Jack L.',
    '9ce50e4f032c45afaa3eca936e99c9db': 'Olivia D.',
    'dea876f23cf9428185f8757955c2eecd': 'Claire E.',
    'e0e0d50ee23443cf80cea1d777fac793': 'Mike D.',
    '37957b35724d4660a62379edd6b4e09c': 'Cindy E.',
    '071c311e3b154327818fe074aeaa3087': 'Jake H.',
    '8d1ba5575516432f851d16bffecc1970': 'Kelsey H.',
}
EXCLUDED = set()  # No exclusions for the family league

# Round themes / descriptive context — used for ordering and commentary keys
ROUND_ORDER = [
    '63ad85e6269e449cbf79ec81e6bb82f2',  # 1 — Songs that make you think of summer
    '6f994c3c334c4472936003d118b4fe22',  # 2 — Song from the year you were born
    '1f5d6adc528145ba997ba0599835e249',  # 3 — World Music Week
    'a900496fb2c940a0a4ad7b834757eb07',  # 4 — Spotify All Time Most Played
    'f7913c626cd94edfbb4fd396796b20f9',  # 5 — Deep Cuts Only
    'b0f83862912a499abbacc52b9c5d644a',  # 6 — Fresh Finds
    '86d7924aef6b493ca9a046c83af34fc7',  # 7 — No Words
    'b2b2de86dcce45e89046a85bcb8bd17a',  # 8 — Covers
    '948835cd6ca942bc9652ffade8a495e3',  # 9 — Closer Entrance Music
]

# Per-round theme config — drives the per-week color palette + body tile
# 'palette' keys map to CSS variables exposed by index.html
ROUND_THEMES = {
    1: {
        'name': 'summer',
        'tile_class': 'theme-sun-bg',
        'palette': {
            'primary':   '#F08A47',  # warmer terracotta (10% saturation push)
            'accent':    '#F4B97A',  # peach
            'cool':      '#4FA0C4',  # sea-glass
            'highlight': '#C25A28',  # sunset deep
            'tile':      '#1f1814',  # body tile color
        },
        'band_gradient': 'linear-gradient(90deg, #4FA0C4 0%, #F4B97A 45%, #F08A47 75%, #C25A28 100%)',
        'design': {
            'band':         'gradient',  # smooth horizon gradient
            'tab_underline':'gradient',  # gradient slice under active tab
            'stat_accent':  'solid',     # 2px solid border-top on cool stat card
            'mark':         'sun',       # sun SVG in round bar
        },
    },
    2: {
        'name': 'cassette',
        'tile_class': 'theme-cassette-bg',
        'palette': {
            'primary':   '#C9824B',  # aged amber
            'accent':    '#D9B68C',  # cream / oat
            'cool':      '#5B7B8C',  # denim slate
            'highlight': '#8B4513',  # saddle brown
            'tile':      '#1c1814',
        },
        # Band is no longer a gradient — it's an inline SVG cassette strip.
        # band_gradient retained as fallback only.
        'band_gradient': 'linear-gradient(90deg, #5B7B8C 0%, #D9B68C 40%, #C9824B 75%, #8B4513 100%)',
        'design': {
            'band':         'cassette',  # cassette-tape SVG strip across full width
            'tab_underline':'spool',     # two dots + connecting line under active tab
            'stat_accent':  'dashed',    # dashed border-top on cool stat card
            'mark':         'play',      # ▶ play button SVG in round bar
        },
    },
    3: {
        'name': 'passport',
        'tile_class': 'theme-passport-bg',
        'palette': {
            'primary':   '#8E2D2D',  # oxblood ink (dominant stamp)
            'accent':    '#E8DCC0',  # aged cream (band paper)
            'cool':      '#2F4A6B',  # airmail ink blue
            'highlight': '#8B5A2B',  # sepia (older stamps / #1 winner)
            'tile':      '#181410',  # deep brown-black (page edge shadow)
        },
        # Band is an inline SVG of stamp impressions on aged paper.
        # band_gradient retained as graceful fallback.
        'band_gradient': 'linear-gradient(90deg, #E8DCC0 0%, #E8DCC0 100%)',
        'design': {
            'band':         'stamps',         # passport-stamp impressions on aged paper
            'tab_underline':'stamp',          # solid oxblood stripe + faint ink-bleed echo
            'stat_accent':  'dotted',         # dotted border-top (perforation reference)
            'mark':         'passport-stamp', # circular stamp impression in round bar
        },
    },
    4: {
        'name': 'histogram',
        'tile_class': 'theme-histogram-bg',
        'palette': {
            # "Personal listening data" palette — deliberately NOT Spotify green.
            # Reads like a stats dashboard / Wrapped recap, warm + electric.
            'primary':   '#E8447C',  # hot magenta (top bars, #1 winner)
            'accent':    '#F2A53C',  # amber (mid bars)
            'cool':      '#5B8DEF',  # periwinkle (accent bars, cool stat card)
            'highlight': '#C9356A',  # deep magenta (peaks)
            'tile':      '#15121A',  # ink-violet page edge
        },
        # Band is an inline SVG histogram (vertical bars of varying height) —
        # a stylized "minutes listened" / equalizer strip. Fallback gradient below.
        'band_gradient': 'linear-gradient(90deg, #5B8DEF 0%, #F2A53C 50%, #E8447C 100%)',
        'design': {
            'band':         'histogram',  # vertical-bar listening histogram across full width
            'tab_underline':'bars',       # small bar-tick cluster under active tab
            'stat_accent':  'bars',       # short bar-chart rule on cool stat card
            'mark':         'histogram',  # tall-bars glyph in round bar
        },
    },
    5: {
        'name': 'constellation',
        'tile_class': 'theme-constellation-bg',
        'palette': {
            # "Hidden / obscure / dig deep" — a night sky of faint connected stars.
            # Deep Cuts = the songs nobody's heard, scattered like distant stars.
            'primary':   '#C9B458',  # pale gold star (#1 winner)
            'accent':    '#8FA9C9',  # silver-blue starlight
            'cool':      '#5E6E94',  # dusk indigo (cool stat card)
            'highlight': '#E4D27A',  # bright star highlight (peaks)
            'tile':      '#0C1020',  # deep midnight page edge
        },
        'band_gradient': 'linear-gradient(90deg, #1A2240 0%, #2A3358 50%, #1A2240 100%)',
        'design': {
            'band':         'constellation',  # connected-dot star map across the band
            'tab_underline':'starline',       # dot-line-dot under active tab
            'stat_accent':  'starpoint',       # small star-tick on cool stat card
            'mark':         'constellation',  # small constellation glyph in round bar
        },
    },
    6: {
        'name': 'sprout',
        'tile_class': 'theme-sprout-bg',
        'palette': {
            # "Fresh Finds / new growth / discovered recently" — spring greens, dewy.
            'primary':   '#5BA861',  # fresh leaf green (#1 winner)
            'accent':    '#A9CC7A',  # young shoot
            'cool':      '#4A9E9E',  # dewy teal (cool stat card)
            'highlight': '#7FC241',  # bright new-growth (peaks)
            'tile':      '#0F1710',  # deep forest page edge
        },
        'band_gradient': 'linear-gradient(90deg, #4A9E9E 0%, #A9CC7A 50%, #5BA861 100%)',
        'design': {
            'band':         'sprout',     # row of small sprouting shoots across the band
            'tab_underline':'vine',       # thin curving stem under active tab
            'stat_accent':  'leaf',        # leaf-tick on cool stat card
            'mark':         'sprout',     # single sprout glyph in round bar
        },
    },
    7: {
        'name': 'waveform',
        'tile_class': 'theme-waveform-bg',
        'palette': {
            # "No Words / instrumental" — the music IS the visual. A single audio
            # waveform. Cool, clean, sound-engineering aesthetic.
            'primary':   '#56C2C2',  # cyan waveform (#1 winner)
            'accent':    '#7E8CE0',  # periwinkle
            'cool':      '#C77DD6',  # orchid (cool stat card)
            'highlight': '#4DD6B0',  # bright aqua (peaks)
            'tile':      '#0B1418',  # deep teal-black page edge
        },
        'band_gradient': 'linear-gradient(90deg, #56C2C2 0%, #7E8CE0 50%, #C77DD6 100%)',
        'design': {
            'band':         'waveform',   # symmetric audio waveform across full width
            'tab_underline':'wave',       # small sine-wave under active tab
            'stat_accent':  'wave',        # wave-tick on cool stat card
            'mark':         'waveform',   # waveform burst glyph in round bar
        },
    },
    8: {
        'name': 'covers',
        'tile_class': 'theme-covers-bg',
        'palette': {
            # "Covers / one song, two versions" — a duotone echo. Warm amber for the
            # original, cool teal for the cover, offset like two pressings of one record.
            'primary':   '#E0964A',  # warm amber (the original; #1 winner)
            'accent':    '#4FB0A8',  # teal (the cover / reinterpretation)
            'cool':      '#4FB0A8',  # teal (cool stat card)
            'highlight': '#E8B45C',  # bright amber (peaks)
            'tile':      '#16130E',  # warm dark page edge
        },
        'band_gradient': 'linear-gradient(90deg, #E0964A 0%, #4FB0A8 100%)',
        'design': {
            'band':         'covers',   # two offset record arcs (original + cover)
            'tab_underline':'echo',     # doubled offset underline (original + cover)
            'stat_accent':  'echo',      # double rule on cool stat card
            'mark':         'covers',   # overlapping dual-record glyph in round bar
        },
    },
    9: {
        'name': 'scoreboard',
        'tile_class': 'theme-scoreboard-bg',
        'palette': {
            # "Closer entrance music" — Wrigley hand-operated scoreboard.
            # Cream numbers + amber accents on deep enamel green.
            'primary':   '#F2B33D',  # amber numerals (#1 winner / lit cells)
            'accent':    '#E0533B',  # red (alert / hot count)
            'cool':      '#39B87A',  # scoreboard green (cool stat card)
            'highlight': '#F7C95B',  # bright amber (peaks)
            'tile':      '#0E2A20',  # deep enamel-green page edge
        },
        'band_gradient': 'linear-gradient(90deg, #1B4A3A 0%, #143A2D 100%)',
        'design': {
            'band':         'scoreboard',  # Wrigley line-score panel
            'tab_underline':'led',         # cream tick row under active tab
            'stat_accent':  'led',          # scoreboard-rule on cool stat card
            'mark':         'scoreboard',  # enamel home-plate glyph in round bar
        },
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def track_id_from_uri(uri):
    return uri.split(':')[-1] if uri else ''

def spotify_url(uri):
    tid = track_id_from_uri(uri)
    return f'https://open.spotify.com/track/{tid}' if tid else ''

def display(pid):
    return PLAYERS.get(pid, f'Unknown ({pid[:8]})')

# ---------------------------------------------------------------------------
# Load CSVs
# ---------------------------------------------------------------------------

def load_csvs():
    rounds = []
    with open(f'{UPLOAD_DIR}/rounds.csv') as f:
        for row in csv.DictReader(f):
            rounds.append({
                'id': row['ID'],
                'name': row['Name'].strip(),
                'description': row['Description'].strip() if row.get('Description') else '',
                'playlist_url': row['Playlist URL'].strip(),
                'created': row['Created'],
            })

    subs = []
    with open(f'{UPLOAD_DIR}/submissions.csv') as f:
        for row in csv.DictReader(f):
            if row['Submitter ID'] in EXCLUDED:
                continue
            subs.append({
                'spotify_uri': row['Spotify URI'],
                'title': row['Title'],
                'album': row['Album'],
                'artist': row['Artist(s)'],
                'submitter_id': row['Submitter ID'],
                'round_id': row['Round ID'],
                'comment': row.get('Comment', ''),
            })

    votes = []
    with open(f'{UPLOAD_DIR}/votes.csv') as f:
        for row in csv.DictReader(f):
            if row['Voter ID'] in EXCLUDED:
                continue
            votes.append({
                'spotify_uri': row['Spotify URI'],
                'voter_id': row['Voter ID'],
                'points': int(row['Points Assigned']),
                'round_id': row['Round ID'],
                'comment': row.get('Comment', ''),
            })

    return rounds, subs, votes


def compute_join_rounds(subs, votes):
    """Determine the earliest round each player was active (submitted or voted) in.
    Returns dict mapping player_id -> round number (1-indexed), or None if never active."""
    rid_to_num = {rid: i+1 for i, rid in enumerate(ROUND_ORDER)}
    first = {}
    for s in subs:
        pid = s['submitter_id']
        rn = rid_to_num.get(s['round_id'])
        if rn and (pid not in first or rn < first[pid]):
            first[pid] = rn
    for v in votes:
        pid = v['voter_id']
        rn = rid_to_num.get(v['round_id'])
        if rn and (pid not in first or rn < first[pid]):
            first[pid] = rn
    return first

# ---------------------------------------------------------------------------
# Build rounds
# ---------------------------------------------------------------------------

def build_rounds(rounds_csv, subs, votes):
    by_id = {r['id']: r for r in rounds_csv}
    ordered = []
    for i, rid in enumerate(ROUND_ORDER, 1):
        if rid in by_id:
            r = dict(by_id[rid])
            r['number'] = i
            ordered.append(r)

    results = []
    for rd in ordered:
        rid = rd['id']
        rd_subs = [s for s in subs if s['round_id'] == rid]
        rd_votes = [v for v in votes if v['round_id'] == rid]

        pts_per_song = Counter()
        voters_per_song = defaultdict(set)
        for v in rd_votes:
            pts_per_song[v['spotify_uri']] += v['points']
            if v['points'] > 0:
                voters_per_song[v['spotify_uri']].add(v['voter_id'])

        # Compute voters_in_round up front so forfeit flag can be applied to songs as they're built
        voters_in_round = {v['voter_id'] for v in rd_votes}

        # Build songs, sorted by forfeit status then total points desc.
        # Songs from submitters who didn't vote get a `forfeited: True` flag and sort to the bottom
        # with their points struck through in the UI.
        songs = []
        for s in rd_subs:
            uri = s['spotify_uri']
            songs.append({
                'title': s['title'],
                'artist': s['artist'],
                'album': s['album'],
                'submitter_id': s['submitter_id'],
                'submitter': display(s['submitter_id']),
                'total_pts': pts_per_song.get(uri, 0),
                'unique_voters': len(voters_per_song.get(uri, set())),
                'spotify_uri': uri,
                'track_id': track_id_from_uri(uri),
                'spotify_url': spotify_url(uri),
                'comment': s.get('comment', '') or '',
                'forfeited': s['submitter_id'] not in voters_in_round,
            })
        # Sort: non-forfeited first (by pts desc, voters desc, title), forfeited last (same tiebreak)
        songs.sort(key=lambda x: (x['forfeited'], -x['total_pts'], -x['unique_voters'], x['title']))

        # FORFEIT RULE
        submitters_in_round = {s['submitter_id'] for s in rd_subs}

        player_pts = defaultdict(int)
        player_pts_earned = defaultdict(int)
        for s in songs:
            player_pts_earned[s['submitter_id']] += s['total_pts']
            if s['submitter_id'] in voters_in_round:
                player_pts[s['submitter_id']] += s['total_pts']
            else:
                player_pts[s['submitter_id']] += 0

        leaderboard = []
        for pid in submitters_in_round:
            leaderboard.append({
                'player_id': pid,
                'player': display(pid),
                'points': player_pts[pid],
                'voted': pid in voters_in_round,
                'pts_forfeited': player_pts_earned[pid] - player_pts[pid],
            })
        leaderboard.sort(key=lambda x: -x['points'])
        rank = 0
        last_pts = None
        for i, e in enumerate(leaderboard):
            if e['points'] != last_pts:
                rank = i + 1
                last_pts = e['points']
            e['rank'] = rank

        # Missed points
        missed = []
        for pid in submitters_in_round - voters_in_round:
            songs_count = sum(1 for s in rd_subs if s['submitter_id'] == pid)
            missed.append({
                'player': display(pid),
                'total_missed': player_pts_earned[pid],
                'songs': songs_count,
            })
        missed.sort(key=lambda x: (-x['total_missed'], x['player']))

        # Generosity — only point-bearing votes count as "songs voted"; comments-without-points
        # are observations, not votes, and should not inflate the denominator or the song count.
        gen_pts = defaultdict(int)
        gen_nonzero_votes = defaultdict(int)
        gen_songs_voted = defaultdict(set)
        for v in rd_votes:
            gen_pts[v['voter_id']] += v['points']
            if v['points'] > 0:
                gen_nonzero_votes[v['voter_id']] += 1
                gen_songs_voted[v['voter_id']].add(v['spotify_uri'])
        generosity = []
        for pid in sorted(voters_in_round, key=lambda p: display(p)):
            nz = gen_nonzero_votes[pid]
            avg = round(gen_pts[pid] / nz, 2) if nz > 0 else 0.0
            generosity.append({
                'player_id': pid,
                'player': display(pid),
                'avg_per_vote': avg,
                'total_songs_voted': len(gen_songs_voted[pid]),
                'total_pts_given': gen_pts[pid],
            })
        generosity.sort(key=lambda x: -x['avg_per_vote'])

        # Vote details — include all non-zero votes plus zero-point rows that carry a comment
        uri_to_song = {s['spotify_uri']: s for s in rd_subs}
        vote_details = []
        for v in rd_votes:
            comment = (v.get('comment') or '').strip()
            # Skip rows that are both 0 points AND have no comment (Music League sometimes
            # writes blank rows for voters who simply scrolled past a song)
            if v['points'] == 0 and not comment:
                continue
            song = uri_to_song.get(v['spotify_uri'])
            if not song:
                continue
            vote_details.append({
                'voter_id': v['voter_id'],
                'voter': display(v['voter_id']),
                'submitter_id': song['submitter_id'],
                'submitter': display(song['submitter_id']),
                'song': song['title'],
                'points': v['points'],
                'comment': comment,
            })

        stats = {
            'total_submissions': len(rd_subs),
            'total_votes': sum(1 for v in rd_votes if v['points'] > 0),
            'unique_voters': len(voters_in_round),
            'unique_submitters': len(submitters_in_round),
        }

        results.append({
            'id': rid,
            'number': rd['number'],
            'name': rd['name'],
            'description': rd['description'],
            'playlist_url': rd['playlist_url'],
            'theme': ROUND_THEMES.get(rd['number'], {}),
            'songs': songs,
            'leaderboard': leaderboard,
            'missed_points': missed,
            'generosity': generosity,
            'vote_details': vote_details,
            'stats': stats,
        })

    return results


# ---------------------------------------------------------------------------
# Commentary
# ---------------------------------------------------------------------------

COMMENTARY = {}

COMMENTARY[1] = {
    "title": "Week 1 Recap",
    "sections": [
        {
            "heading": "The lay of the land",
            "text": "Eleven family members, one round in, with one already on the Ghost Report and another sitting at the top of the standings. Round 1 set a baseline for what this league cares about: a deeply contested middle, a couple of warm and obvious crowd-pleasers up top, and a pair of cool-but-divisive picks that turned into the round's most interesting tells. Below: what the data says about Round 1, and what the season's first signal-readings suggest about the weeks ahead."
        },
        {
            "heading": "How Olivia D. won (and how it almost went a different way)",
            "text": "Olivia took Round 1 with 19 points across two submissions — \"Ants Marching\" (13 pts, 6 voters) and \"Gimme! Gimme! Gimme!\" from Mamma Mia! (6 pts, 5 voters). What's notable is the shape of the win: she had the round's second-highest single-song score AND a strong second submission. That's a balanced playbook.\n\nCompare to Dray E., who finished 3rd with 16 points but pulled it off with one big swing — Tim McGraw's \"Something Like That\" took Song of the Week at 14 points, but his second submission (Buffett's \"Hurricane Season\") only mustered 2. One blockbuster + one whiff = third place. One strong + one solid = first."
        },
        {
            "heading": "The most efficient round of the season (so far)",
            "text": "Claire E. submitted two songs and landed both in the top four. \"Soak Up The Sun\" finished 3rd at 10 points, \"Chicken Fried\" finished 4th at 8 points. That's 18 total points and a 9.0 average per submission — the round's best. The Submission Efficiency metric on the Season tab tracks this number across the full season; right now Claire is the league benchmark to beat. Olivia is technically slightly higher at 9.5 average, but Claire's both songs cracked top 4, and both were universally well-received (5 and 6 voters respectively). Sustainable taste."
        },
        {
            "heading": "Reading the Fun Metrics tab — what the numbers mean",
            "text": "Quick guided tour of what's living on the Season tab, because most of these are easy to skim past:\n\n• Kingmaker — the voter who poured the most points into the eventual weekly winner. Useful for spotting people with a feel for what the room will reward. This week: Olivia D. (4 points to \"Something Like That\"). Olivia chose her round-winning submissions AND voted for the song-of-the-week winner. Keep an eye on her predictions.\n\n• Hipster — share of votes cast for songs nobody else voted for. Tracks taste isolation. This week: Dray E. at 20% solo (2 of his 10 votes went to songs only he liked). One of those was for \"Sonate Pacifique,\" which received 3 total points across 3 voters and was on no one's radar. Dray's a decent indicator of which deep cuts are landing for nobody.\n\n• Sheep — share of points given to consensus picks (songs with 3+ voters). High Sheep score = you're voting with the crowd. This balances Hipster.\n\n• Submission Efficiency — average points earned per song submitted. The league's most useful single number for who's actually picking well. Currently led by Olivia (9.5), Claire (9.0), Dray (8.0).\n\n• Snub Detector — songs that got lots of voters but very few points each. The signature pattern: 5 voters all gave it 1 point. Universally acknowledged, universally not loved. This round caught two: \"Mamma Mia!\" (5 voters, 6 pts, 1.2 avg) and \"Texas Sun\" (5 voters, 6 pts, 1.2 avg). Both songs nobody dared give a zero, but nobody felt strongly about either."
        },
        {
            "heading": "The most divisive submission of the round",
            "text": "\"Walking On Sunshine\" by Katrina & The Waves was the single hardest song to predict and it confounded everyone. The blind report had it pegged as the round winner. It finished 14th with 3 points from 2 voters. That's an enormous miss.\n\nThe likely explanation: when a song is *too* obviously the right answer to a music league prompt, voters punish it as low-effort even when the actual song is good. \"Soak Up The Sun\" cleared this hurdle — same energy, better outcome — possibly because Claire's submitter comment about windows down and sun roof open framed it as personal rather than obligatory. Lesson for Round 2 submitters: if your song is the literal answer to the prompt, you need to bring something that earns it."
        },
        {
            "heading": "The Ghost Report",
            "text": "10 of 11 family members submitted. 10 of 11 voted. Steve E. did neither. The Ghost Report on the Season tab tracks players who have never voted; right now there's exactly one entry, and the standings show Steve at 0 points with 11 rounds to go. The good news is the comeback story is still wide open. The bad news is the league is keeping receipts."
        },
        {
            "heading": "Storyline to track: the couples are voting, but not equally",
            "text": "Every player in the league right now is half of a couple, and every couple is in the league together. That sets up an interesting wrinkle: do partners vote for each other? Round 1 says yes — but only in one direction.\n\nLook at the affinities:\n• Tess D. → Jack L.: 5 pts. Jack L. → Tess D.: 0 pts.\n• Mills T. → Olivia D.: 5 pts. Olivia D. → Mills T.: 1 pt.\n• Claire E. → Dray E.: 4 pts. Dray E. → Claire E.: 1 pt.\n• Gabriel M. → Elyse E.: 2 pts. Elyse E. → Gabriel M.: 0 pts.\n• Mary D. → Mike D.: 1 pt. Mike D. → Mary D.: 1 pt. (the only balanced couple)\n\nFour of five couples were lopsided, and the lopsided direction was consistent: the partners-by-marriage and the in-laws gave more than they got back. Is this collusion? Familiarity (you already know your partner's taste, so you know which submission to back)? Or just noise from a single round? Hard to say with one data point. But we'll be tracking the couples-voting symmetry index every week, and if Tess keeps backing Jack while Jack keeps freezing her out, this becomes a season-long storyline."
        },
        {
            "heading": "The Dillon bloc is real",
            "text": "Family voting cuts even cleaner than couples voting. The Dillons (Claire, Olivia, Tess, Mary, and Mike) gave 25 points to other Dillons across 19 votes. The Ensors (Dray, Elyse) gave 5 points to other Ensors across 3 votes. Partners (Mills, Jack, Gabriel) gave 15 points to Dillons but only 5 points to each other.\n\nSome of this is just population — there are five Dillons and only two active Ensors. But not all of it. Claire received 18 points total, tied with Olivia for the round's most-loved submitter. Of those 18, twelve came from Dillons + Mike + a partner who married in. Dray received 16, with the same pattern: family and family-adjacent voters carrying the load. Round 1 confirms the obvious: it pays to have more siblings in the league."
        },
        {
            "heading": "Where the standings actually stand",
            "text": "Olivia (19), Claire (18), and Dray (16) are bunched at the top with only 3 points separating them. Eight of 11 players are within 8 points of first place. With 11 rounds still to go, this is wide open — one strong week vaults anyone into contention. Round 1 was a calibration round. Round 2 is where the signal starts."
        },
        {
            "heading": "Blind report scorecard",
            "text": "Predicted top 5: Walking On Sunshine, Summer Nights, Steal My Sunshine, Soak Up The Sun, Hurricane Season. Actual top 5: Something Like That, Ants Marching, Soak Up The Sun, Chicken Fried, Steal My Sunshine. Two correct, three misses (one catastrophic — Hurricane Season finished 16th). Predicted bottom 3 was a complete miss (Sonate Pacifique 12th instead of last, Hot In Herre 9th instead of bottom). The model needs more rounds of data — submitter taste profiles will be much sharper by Week 3 once we can correlate picks across rounds."
        }
    ]
}

COMMENTARY[4] = {
    "title": "Week 4 Recap",
    "sections": [
        {
            "heading": "Scouting Report (written blind)",
            "text": "The blind report was committed before votes were revealed, submitter IDs stripped from the upload. This was the no-game round — \"your two most-played songs of all time\" can't be strategized, so the submissions were pure taste confessions. Top 5 prediction: September, Bohemian Rhapsody, You Make My Dreams, I Want It That Way, Dreams. Song of the Week pick: September. Dark horse: I Want It That Way (Backstreet Boys). Predicted zeros: Cool to You, Shines, Sueño de una noche de verano. The scorecard at the bottom has the verified results."
        },
        {
            "heading": "Mary D. wins the round — and posts the best single-round total of the season",
            "text": "Mary D. took Round 4 with 21 points across her two submissions: Brandy (You're a Fine Girl) by Looking Glass won the round outright at 14 points, and Bohemian Rhapsody added 7 more. That 21-point haul is the highest single-round score any player has posted all season, edging Mills T.'s 20-point Week 2.\n\nBrandy won in the most democratic way possible: 9 of 11 voters gave it points, and not one of them gave it more than 2. Five 2-point votes (Steve, Jack, Tess, Claire, Elyse) and four 1-point votes (Mills, Mike, Gabriel, Dray). No whale vote, no bloc — just near-universal mild affection for a 1972 one-hit-wonder soft-rock song. That is the platonic ideal of a consensus winner: nobody's favorite, almost everybody's fine-with-it.\n\nMary's submitter comment on Brandy was disarmingly honest: \"My number two. I've only been on Spotify since 2020.\" She's the only player who flagged that her \"all-time most played\" data is actually just a five-year window — which, given that she still won the round with it, suggests Mary's five years of Spotify are more potent than everyone else's twenty."
        },
        {
            "heading": "Steve E. emerges from the void, and he brought the whole party",
            "text": "Steve E. entered Week 4 with a season scoreline of 0, 2, 0 — two ghostings and one near-miss across three rounds. In Round 4 he scored 16 points (September at 11, I Want It That Way at 5), good for the second-highest individual round total of the week behind only Mary.\n\nHere's the kicker for the blind report: the two songs I predicted #1 and #4 in the entire round — September and I Want It That Way — were *both* Steve's. The model nailed the picks and had no idea they came from the player who'd done the least all season. September pulled 11 points and 8 voters, with Tess leaving the comment of the round: \"*involuntarily begins shaking ass*.\" Mary gave September 2 points with \"This song is the anthem of my college years! So glad it's still relevant.\" Steve's 16-point round vaults him from dead last to 10th, finally clear of the basement."
        },
        {
            "heading": "The no-game round confirmed everything the echo chamber theory predicted",
            "text": "Because nobody could strategize this round, the results map the family's actual shared taste with unusual clarity. The top of the board is dominated by the universally-legible: Brandy (14), Dreams by Fleetwood Mac (13, Claire), September (11, Steve). All three are cross-generational, instantly familiar, hard-to-dislike songs.\n\nThe bottom of the board is exactly where genuine personal taste went to get filtered out by shared unfamiliarity. The two true zeros were Cool to You by Teenage Priest (Tess) and It's Strange by Louis the Child feat. K.Flay (Elyse) — both lower-recognizability tracks that scored zero not because they're bad but because nobody else in the family had the context to reward them. The two Brazilian most-played tracks (Gabriel's Mandona and Deixe Me Ir) managed just 1 point each. Genuine daily-listening favorites, filtered to the floor.\n\nThat's the dynamic in miniature: the songs the whole family already shares rise; the songs that would actually expand anyone's horizons sink. Useful confirmation heading into future rounds."
        },
        {
            "heading": "Standings: Claire pulls clear, Mary storms the top four",
            "text": "Claire E. now leads the season at 58 points, 12 clear of Mills T. (46). Claire has placed in the top tier every single round since Week 1 and is the only player who has never had a bad week — her four-round line is 18-10-15-15, remarkably steady. She didn't even win Round 4 (Dreams finished 2nd at 13) and still extended her lead.\n\nThe big mover is Mary D., whose 21-point round rockets her from 9th to 4th (42 points), now within striking distance of Olivia (45) and Mills (46). Mike D. and Dray E. are tied at 36. The bottom two are Gabriel M. (17, hurt badly by the Week 3 forfeit) and Steve E. (18, climbing).\n\nFour rounds, four different round winners: Olivia, Mills, Claire, Mary. The league still has no repeat champion, but it does now have a clear season frontrunner for the first time."
        },
        {
            "heading": "Couples voting: the point-weighted picture after four rounds",
            "text": "Recomputing the partner-bonus ratios (how each person scores their partner versus everyone else) with Round 4 folded in:\n\nTess → Jack remains the strongest tilt in the league at 1.42×. Tess gives the average submitter 1.76 pts/vote but Jack gets 2.50, and she's now spent 10 of her cumulative points on him.\n\nClaire → Dray sits at 1.14×, Mills → Olivia at 1.17×, Jack → Tess at 1.12×, Mike → Mary at 1.04×, Mary → Mike at 1.06× — a cluster of mild, healthy positive tilts.\n\nThe notable update: Olivia → Mills moved from 0.50× last week to 1.00× this week. After looking underweighted in Week 3, Olivia evened things out in Round 4, and her cumulative ratio is now neutral — she scores Mills exactly as she scores the field. The Week 3 \"phoning it in\" read has corrected itself with more data. The only sub-baseline direction left is Elyse → Gabriel at 0.67×.\n\nAnd Dray → Claire stays locked at 1.00× for the structural reason it always will: Dray gives ten 1-point votes to ten different songs every single week. He has never given anyone a 2. He mathematically cannot favor a partner, so his 1.00× is less a verdict on the marriage than a verdict on his voting style."
        },
        {
            "heading": "Blind report scorecard",
            "text": "Top 5 prediction vs. actual: September predicted #1, finished #3 (11 pts) — within ±2. Dreams predicted #5, finished #2 (13 pts) — within ±3. Bohemian Rhapsody predicted #2, finished #6 (7 pts) — within ±4. I Want It That Way predicted #4 (and tagged dark-horse top-3), finished #10 (5 pts) — a clear miss; the family did not lean into the Backstreet Boys nostalgia the way the model bet they would. You Make My Dreams predicted #3, finished #18 (2 pts) — a catastrophic miss, the model's worst single call of the season. \"Universal warmth, zero haters\" turned out to be two points and near-total indifference.\n\nThe winner was missed entirely: Brandy was tagged only as a \"sleeper, could overperform on warmth,\" not as the #1. So the model identified the right *quality* (broad mild affection) but pinned it to the wrong song.\n\nZero-vote predictions: 1 of 3 clean. Cool to You was correctly called for zero — exact hit. Shines finished 2 points (close). Sueño de una noche de verano was the miss — predicted bottom-3, actually finished 9th with 6 points, the round's biggest overperformance relative to prediction. And It's Strange hit zero without being predicted.\n\nCumulative across four rounds: the model is good at identifying which songs will cluster near the top, weak at picking the exact winner, and consistently wrong about consensus pop (it overrates universally-known songs like You Make My Dreams and the Backstreet Boys, which the family treats as background rather than vote-worthy). Adjustment for Round 5: stop assuming maximum-recognizability equals maximum points. In this family, the song everyone knows is often the song nobody bothers to rank."
        }
    ]
}

COMMENTARY[3] = {
    "title": "Week 3 Recap",
    "sections": [
        {
            "heading": "Scouting Report (written blind)",
            "text": "The blind report was committed before votes were revealed, with submitter IDs stripped from the submissions CSV for the first time this season. Top 5 prediction: La Vie en rose (winner), 99 Luftballons, Dancing Queen, Many Rivers To Cross, Volare. Zero-vote calls: Conselho, Vaitimbora, Favourite. Dark horse: Fantastic Man by William Onyeabor. Sneaky floor: Highway to Hell. Theme reading: a Brazil bloc of 5 songs (23% of the playlist) would cannibalize itself, and the 10 English-language picks (45% of the playlist, in defiance of the prompt's \"preferably no English\" soft constraint) would collectively underperform. See the scorecard at the bottom for what actually happened."
        },
        {
            "heading": "Claire E. wins the round with the most theme-pure pick on the playlist",
            "text": "99 Luftballons — Nena, 1983, German, anti-war Cold War classic — picked up 13 points from 7 of the 9 voters in the round (78% reach), the broadest support any song has received in three weeks. Jack L. dropped the only 4-point vote of the entire round on it. Olivia D. backed it with a 3. The other 5 voters who awarded points (Elyse, Dray, Mills, Mary, Mike) each contributed 1 or 2.\n\nThis is the cleanest win the league has produced so far. Round 1 was won by an emotional storytelling combo (Olivia's Ants Marching + Mamma Mia). Round 2 was won by pure radio recognition (Mills's All Star + Scar Tissue). Round 3 is the first time the league has rewarded *theme-fit* above all else — Nena is the rare song that achieved global pop status while remaining in its original language, which is exactly what \"world music\" is asking for. Claire's submitter comment, in its entirety: \"How can you not.\" That is the energy of a player who already knew she'd won. Claire jumps from #1 by 1 point in the season to #1 by 10 points. The season's first repeat top-finisher is starting to look like a contender."
        },
        {
            "heading": "Olivia submitted Daddy Yankee in a no-Americans week",
            "text": "Let's just get this on the record. Olivia D. submitted Gasolina by Daddy Yankee. The theme was World Music Week. The description specified \"non-American bands.\" The description further specified \"You can search for the band/artist in Wikipedia and check the origin field to verify.\" Wikipedia's entry on Daddy Yankee, in the very first sentence, lists his nationality as American. Puerto Rico is a US territory. The song he picked is *literally about an American product*, which is, conservatively, the most American thing one could submit in a week about not submitting American things.\n\nDray dropped a single-word zero-point comment: \"American!\" Mills T. — Olivia's fiancé — gave it a 1-point pity vote. Everyone else, including her own siblings, sailed past it."
        },
        {
            "heading": "Mike D. is still using this league as a Paris travelogue",
            "text": "Mike D.'s submitter comment on La Vie en rose (which finished 2nd at 7 points): \"Olivia played this song for us on repeat - Permanently linked to Paris and place de la contrascarpe.\" Translation: Mike and Mary recently went to Paris with their daughter Olivia, who played them La Vie en rose enough times that it became the soundtrack of the trip. That comment is now permanently associated with a Music League submission, which makes it part of the family record.\n\nMike has now used three consecutive rounds to commemorate Dillon family events through music — Round 2 had the wedding-song double-submission (Moon River for Olivia/Mills, Can't Help Falling in Love for Claire/Dray); Round 3 catalogs a recent Paris trip. He's not playing for points. He's playing for posterity. La Vie en rose finishing 2nd at 7 points is also his highest single-song total of the season. Of the 7 points it earned, 3 came from Olivia D. — meaning the daughter who played the song in Paris voted for the song her father submitted about her playing the song. That's a closed loop. That's family."
        },
        {
            "heading": "The Brazil bloc was three submitters, not one — and they cannibalized themselves anyway",
            "text": "The blind report flagged 5 Brazilian submissions and bet that one submitter had gone deep on Brazilian music. Reveal: it was three different submitters splitting the bloc. Dray E. submitted Maria fumaça (Banda Black Rio). Elyse E. submitted Vaitimbora (Mari Froes/Trinix) and Conselho (Samba De Raiz). Gabriel M. submitted Coração Radiante (Grupo Revelação) and We Are The World Of Carnaval (Banda Eva). The Magalhães-Ensor household alone produced 4 of the 5 Brazil picks; Dray added the fifth from the partner desk.\n\nCannibalization happened anyway. Brazil bloc averaged 3.4 points per song versus 4.3 for non-Brazil songs. 19% of total round points went to 23% of the playlist. The two strongest Brazil performers were Coração Radiante (5 pts, 5 voters — Gabriel's best song) and Vaitimbora (4 pts, 3 voters — which avoided the predicted zero-vote outcome). Dray's Maria fumaça scored 3 from Elyse (2) and Claire (1). Brazil is now a known taste signature for three players — the longest 248-word submitter note of the season was Dray's on Maria fumaça, explaining the entire Banda Black Rio mythology, and people apparently read it (Elyse's 2-pointer is the highest single vote any Brazilian song received this week)."
        },
        {
            "heading": "The English-language penalty was real",
            "text": "10 of 22 songs were in English. They collectively pulled 36 of 90 total points (40%). That's an English-song average of 3.6 vs. a non-English average of 4.5 — a 25% performance gap. The prompt said \"preferably no English\" and the family voted accordingly, just not enough to flip the leaderboard: Wavin' Flag (English, but the Coca-Cola Celebration Mix in a world-music week) still finished tied for 3rd at 6 points; My Sweet Lord (George Harrison, English) tied for 3rd with it. The most punished English picks: Highway to Hell (AC/DC, 1 point, 1 voter — tied for last with Gasolina) and Favourite (Fontaines D.C., 2 points, 1 voter — that voter being Tess D., the lone Fontaines D.C. fan in the family).\n\nMeaning for future weeks: when a theme has a soft constraint, this league takes it seriously. The voting majority is willing to penalize song quality in service of theme discipline. Submitters who ignored the constraint paid for it. The sneaky-floor prediction held — AC/DC got exactly the 1-point pity vote it was forecast to receive, courtesy of an as-yet-unnamed voter who clearly couldn't bring themselves to skip the song entirely. Worth noting: Highway to Hell was submitted by Steve E., whose own comment read \"This actually an Australian band. Never knew that.\" Steve genuinely didn't know AC/DC was Australian when he submitted the song. He learned it in the act of submitting. That's the family league experience in one comment."
        },
        {
            "heading": "The dark horse hit, exactly as predicted",
            "text": "Fantastic Man — William Onyeabor — was called as a dark horse in the blind report on the theory that \"if even 3 voters know who Onyeabor is, this hits top 8.\" Final: 5 points, 3 voters, tied for 5th. **Exact landing on both the voter count AND the rank.** The 3 voters were Claire E. (2 pts), Tess D. (2 pts), and Mike D. (1 pt). The 248-word Onyeabor mythology comment from the submitter (Dray E.) appears to have done its job — these three voters read it and rewarded the song. Claire's vote comment said it best: \"The Dillon's love it. Dray is this. Good submission.\" Translation: Onyeabor is a Dillon-coded artist now. Also, Claire just declared her husband to be a 1970s Nigerian synth-funk recluse. Make of that what you will."
        },
        {
            "heading": "Ghost Report: the void reopens",
            "text": "Last week we welcomed Steve E. back from the inaugural Round 1 ghosting and declared the Ghost Report empty. This week, Steve E. did the unthinkable: he submitted (Dancing Queen and Highway to Hell), but he didn't vote. Under the league's forfeit rule, his two songs earned 4 raw points from real voters and Steve receives zero. Worse: Gabriel M. also didn't vote, which forfeits the 7 raw points his two Brazilian songs earned. Coração Radiante's 5 points and Carnaval's 2 points both vanish from the standings.\n\nThat's a 7-point forfeit for Gabriel and a 4-point forfeit for Steve. Gabriel goes from a hypothetical 4th place in the round to dead last with 0. Steve stays stuck at 2 season points. As of this week, the song cards on the Weekly tab now sort forfeited submissions to the bottom of the list with their point totals struck through — a permanent visual reminder of what happens when you submit but don't vote. Steve's Dancing Queen had a submitter comment that said \"I don't love this song but women do so I'm trolling for votes.\" The trolling worked — Dancing Queen pulled 3 points from Elyse, Mary, and Olivia. Then Steve forgot to vote and forfeited all three. Ghost Report on the Season tab now has two names again."
        },
        {
            "heading": "Couples voting: it's not the totals, it's the points distribution",
            "text": "I've been measuring couples voting wrong. Just summing the points each partner sends to the other treats every vote as equal, but in this league it absolutely isn't. Dray gives 10 different songs 1 point apiece every single week. Olivia gives a handful of songs 3 or 4 points apiece. \"Dray gave Claire 3 points\" and \"Olivia gave Mills 2 points\" sound similar on a leaderboard but they're completely different signals — one is Dray's *literal maximum possible expression of approval over three rounds*, the other is Olivia phoning it in.\n\nThe right metric is **partner-bonus ratio**: how the voter scores their partner compared to how they score everyone else. Here's where the couples actually stand after 3 rounds, ranked by signal strength:\n\n**Tess → Jack: 1.50× baseline.** Tess gives the average submitter 1.67 pts/vote, but Jack gets 2.50 pts/vote across 4 songs. She has spent 10 of her 30 cumulative points (33%) on Jack alone. Strongest positive signal in the league.\n\n**Claire → Dray: 1.31× baseline.** Claire baselines 1.22, Dray gets 1.60. Importantly, the only 3-point vote Claire has dropped across three rounds went to Dray (for Something Like That in Week 1). Her biggest single expression of approval, on her highest-conviction vote of the season, was for her husband.\n\n**Mills → Olivia: 1.14× baseline.** Average is modest, but Mills's single highest vote this season — a 3-pointer for Ants Marching — went to Olivia. So his *peak* attention is on her, even if his average isn't dramatically tilted.\n\n**Jack → Tess: 1.00× baseline.** Jack gives Tess exactly his average. Notable because his single highest vote ever — a 4 to Claire's 99 Luftballons — and his next-highest — a 3 to Mills's All Star — both went elsewhere. Tess gets Jack's baseline; his big swings go to family.\n\n**Mike → Mary: 1.06× baseline.** Mike treats Mary like he treats everyone, which for Mike is consistent low-key engagement. But here's the wrinkle: Mike has dropped exactly two 4-point votes this season — both for Claire (Smells Like Teen Spirit and Chicken Fried). He's never given Mary a 4. He gives his daughter his peak attention; his wife gets the mode.\n\n**Gabriel → Elyse: 0.92× baseline.** Slight underweighting. Gabriel's highest single vote ever is a 2 — he simply doesn't make peak gestures. So nothing dramatic, but also no special treatment.\n\n**Mary → Mike: 0.92× baseline.** Effectively flat. Mary baselines 1.08 (she's the league's most generous spreader by raw vote count, 28 votes), and Mike gets exactly 1.00 from her.\n\n**Elyse → Gabriel: 0.63× baseline.** Elyse averages 1.59 to other submitters but Gabriel gets 1.00. Her single highest vote — a 3 — went to Claire (Soak Up The Sun), not Gabriel. The partner is *underweighted* compared to non-partners.\n\n**Olivia → Mills: 0.50× baseline.** The spiciest finding in the dataset. Olivia averages 2.00 pts/vote, which is high — she clusters her points on fewer songs. Mills gets exactly 1.00 from her across the two songs she's voted for him on. Her single highest vote this season — a 4 to Dray's Something Like That — did not go to her fiancé. Her two 3-point votes both went to her dad (Moon River, La Vie en rose). Her third 3-pointer went to Claire (99 Luftballons). Mills is currently the 4th-highest-priority recipient of Olivia's point distribution, behind Dray, Mike, and Claire.\n\n**Dray → Claire: 1.00× of 1.00.** Dray spreads 10 1-point votes across 10 different songs every week. He cannot give Claire a bonus because he doesn't give anyone a bonus. His top single vote ever is a 1. To Dray's credit, he has voted for Claire 3 of 3 weeks she's submitted, so the 1.00× baseline is essentially \"Dray's maximum possible expression of approval.\" That's a different signal than Olivia's 1.00 to Mills.\n\nThe story: three couples have one partner who clearly weights the other above the rest of the field (Tess→Jack, Claire→Dray, Mills→Olivia). One couple has both partners running at baseline (Mike & Mary). Two couples have one partner *underweighting* their other (Elyse→Gabriel, Olivia→Mills). And one partner (Dray) is operating in a flat-distribution mode that mathematically cannot favor anyone. We'll keep watching."
        },
        {
            "heading": "Standings: Claire pulls away, the middle tightens up",
            "text": "Claire E. is now the runaway season leader at 43 points, 10 ahead of a two-way tie at #2 between Elyse E. and Mills T. (33 each), with Olivia D. one point further back at #4 (32) and Dray E. fifth (31). Five players are clustered between 31 and 33 points. Mike D. and Jack L. both move up to a tie at #6 with 28 points. Tess D. has the most dramatic week-over-week jump of any player: she was dead last among active members at 12 points and rockets to #8 at 23 by virtue of an 11-point week from just two songs and four voters (an absurd points-per-voter rate). Mary D. drops from T-#8 to #9 after a 6-point round. Gabriel M. is now #10 at 15 — the forfeit penalty froze him in place while everyone except Steve passed him.\n\nThree rounds, three different round winners (Olivia, Mills, Claire). Three rounds, three different last-place finishers (Mary T-9th W1, Tess W2, Gabriel + Steve tied W3 by forfeit). Pattern stability remains zero. The only durable storyline is that voting consistently across weeks is mathematically more important than scoring big in any single one. Mike D. has 4-13-11 across three rounds and is now T-#6 at 28 points — quietly the most consistent submitter in the league. Mills T. has 7-20-6 and is two points further up the table at 33. Volatility wins weeks; consistency wins seasons."
        },
        {
            "heading": "Blind report scorecard",
            "text": "Top 5 prediction (in order): La Vie en rose, 99 Luftballons, Dancing Queen, Many Rivers To Cross, Volare. Actual top 5: 99 Luftballons (winner, 13 pts), La Vie en rose (7), then a 4-way tie at 3rd-place with 6 points (Wavin' Flag + My Sweet Lord), and a 4-way tie at 5th-place with 5 points (Coração Radiante, Fantastic Man, Mi Gente, Volare).\n\nScoring: 99 Luftballons predicted #2, actual #1 — hit within ±1. La Vie en rose predicted #1, actual #2 — hit within ±1. Volare predicted #5, actual T-5th — exact. That's 3 of 5 predictions within ±2 ranks. Dancing Queen badly missed (predicted #3, actual tied for 13th — Steve's troll-for-votes strategy got only as far as 3 points, then the forfeit zeroed it out). Many Rivers To Cross also missed (predicted #4, actual T-14th).\n\nZero-vote predictions: 0 of 3. Conselho got 3 pts. Vaitimbora got 4. Favourite got 2. No song received zero points in Week 3. That's a fascinating data point — the family is more generous than the model expected. The 1-point pity vote is doing a lot of work in this league.\n\nDark horse: Fantastic Man predicted top 8 if 3 voters knew Onyeabor; actual T-5th with exactly 3 voters. **Exact landing.** Sneaky floor: Highway to Hell predicted 8–12 points; actual 1 point. Big miss — the English-language penalty was steeper than the model expected.\n\nCumulative blind report record across 3 weeks: top-5 predictions are improving (Week 3 was the model's best), zero-vote predictions are getting *worse* (0/3 after going 1/3 in W1 and 1/1 in W2), and the framework keeps overestimating consensus picks while underestimating the family's willingness to enforce theme discipline. Round 4 adjustment: be less confident about \"obvious\" picks, more confident about theme-pure picks, and stop predicting any song to score zero unless it's both off-theme AND from an unfamiliar artist."
        }
    ]
}

COMMENTARY[2] = {
    "title": "Week 2 Recap",
    "sections": [
        {
            "heading": "Mills T. wins from the middle of the pack",
            "text": "If Round 1 was won on emotional storytelling (Olivia's Ants Marching + Mamma Mia combo), Round 2 was won on pure radio-friendly recognition. Mills T. submitted \"All Star\" by Smash Mouth and \"Scar Tissue\" by Red Hot Chili Peppers — neither one a deep cut, both pulling 6+ voters apiece. Final tally: 20 points across two songs, the highest individual round score so far. Mills jumps from a tie for 6th last week (7 pts) to a tie for 2nd in the season (27 pts). The man understands his audience: 11 family members across two generations, all of whom have heard \"All Star\" approximately 800 times in their lives, and most of whom are still willing to give it 2 points anyway."
        },
        {
            "heading": "The blind report's whole framework was wrong",
            "text": "Going into Round 2, the prediction was that the parents' wedding-narrative submissions would dominate (the Moon River and Can't Help Falling in Love comments were both intimate family callouts). Reality: those songs landed 5th and 13th respectively. The wedding-song-of-Claire-and-Dray finished BELOW Wonderwall.\n\nThe lesson: in this league, identification with a song matters more than emotional context. The 30-something millennials make up the voting majority, and they're going to reward songs they personally love over songs the parents tell heartfelt stories about. Mike D. submitted both wedding songs (Moon River for Olivia & Mills, Can't Help Falling in Love for Claire & Dray) and walked away with a respectable 13 points across them — but the round was won by Smash Mouth. Calibrate accordingly for Round 3 predictions."
        },
        {
            "heading": "Mike D. is the family's emotional backbone",
            "text": "A subplot worth tracking: Mike D. didn't just submit one wedding song, he submitted both wedding songs of the league. Moon River for the Olivia & Mills wedding (still upcoming) and Can't Help Falling in Love for the Claire & Dray wedding (already happened). That's a *pattern.*\n\nMike isn't playing to win the league — he's playing to commemorate the family. Whether that's a sustainable strategy for points (it isn't, based on this round) or whether he's playing a different game entirely (he is) is a question that will unfold over the season. For now: keep an eye on Mike's submissions for personal-narrative tells about Dillon family history."
        },
        {
            "heading": "Sober (TOOL) is the league's first true zero",
            "text": "Dray E. submitted \"Sober\" by TOOL. It received 0 points and 0 voters. Not a single member of the family rewarded it with even a 1-point pity vote. That's the first true zero-zero shutout in Fam Music League history, and it's already enshrined in the Cold Shoulder metric on the Season tab.\n\nDray's other submission (\"Elderly Woman Behind the Counter in a Small Town\" by Pearl Jam) finished a respectable 7th at 7 points — so the strategy of \"one safe pick + one chaos pick\" earned him 7 points instead of the 14+ a more conventional millennial-radio playbook would have produced. The Hipster metric loves this. The leaderboard does not."
        },
        {
            "heading": "Couples voting: the plot thickens (or thins, depending on how you read it)",
            "text": "Round 1's headline storyline was that couples were voting for each other but only in one direction. Round 2 says: maybe not? Look at the per-round numbers:\n\n• Dray ↔ Claire: 1 ↔ 1 (balanced)\n• Olivia ↔ Mills: 1 ↔ 1 (balanced)\n• Tess → Jack: 3, Jack → Tess: 2 (asymmetry of just 1)\n• Elyse → Gabriel: 1, Gabriel → Elyse: 2 (asymmetry of just 1)\n• Mary ↔ Mike: 1 ↔ 2 (asymmetry of 1)\n\nEvery couple was within 1 point of balanced this week. The Round 1 asymmetries (Tess→Jack 5–0, Mills→Olivia 5–1) didn't repeat. Two possibilities: (a) Round 1 was small-sample noise that happened to look like a pattern, or (b) people read the Week 1 recap and adjusted. The cumulative pattern still shows asymmetry across both rounds (Tess has now given Jack 8 pts to his 2; Olivia owes Mills 4 net), but if Round 3 stays balanced we declare the couples-voting saga officially uncorrelated and move on."
        },
        {
            "heading": "The era split was real, but it didn't predict votes",
            "text": "The Round 2 playlist had a clean demographic split — 6 songs from 1960–63 (the parents' era) and 16 songs from 1991–99 (the kids' era), with a 28-year hole in the middle confirming this league has no Gen-Xer. So far so neat.\n\nBut the predicted dynamic — that the era split would create cross-generational voting friction — didn't really materialize. The Boomer-era picks didn't all flop (Twist & Shout 8th, Moon River 5th, Ring of Fire 11th) and the millennial picks weren't uniformly strong (Believe 14th, Iris 15th, Whoomp 21st). The actual top 4 was a mix: All Star (1999), Run-Around (1994), Smells Like Teen Spirit (1991), Scar Tissue (1999). Pure peak-90s alt-radio. The era didn't matter — the voting majority's age bracket did."
        },
        {
            "heading": "Standings shake-up: nobody's where they were last week",
            "text": "Round 1's leader (Olivia, 19 pts) is now T-3rd in the season at 26 pts. Round 1's third-place (Dray, 16 pts) is now 5th at 23. The new leader is Claire E. at 28 pts — one point ahead of Mills (27), then Elyse and Olivia tied at 26. Five players are within 5 points of first. Tess D., who was T-6th last week, is now dead last among active members at 12 pts (Steve passed her this week with 2 pts, but he's still recovering from his Round 1 ghosting).\n\nTwo rounds in, this league has absolutely zero pattern stability — anyone who finishes below the median in Round 3 was probably going to finish below the median anyway. Which means we're starting to learn things about real taste alignment, not just first-round noise."
        },
        {
            "heading": "Steve E. emerges from the void",
            "text": "Last week: 0 submissions, 0 votes, the inaugural Ghost Report inductee. This week: 2 submissions, 11 votes cast (he showed up for everyone), and 2 points earned. The points are modest (\"Save the Last Dance\" 19th with 1 pt, \"Itsy Bitsy Bikini\" 20th with 1 pt — both struggled to break through against the millennial radio onslaught), but the participation is what matters. The Ghost Report is now empty. Welcome back, Dad."
        },
        {
            "heading": "Blind report scorecard",
            "text": "The blind report predicted Can't Help Falling in Love to win the round. It finished 13th. Predicted Moon River top 2; finished 5th. Predicted Smells Like Teen Spirit top 5; finished 3rd. Predicted Sober bottom 3; finished dead last with 0 points (the prediction was correct, but underestimated the magnitude — \"bottom 3\" wasn't sharp enough; it should have said \"goose egg\"). Predicted submitter for Moon River as Mary D.; was actually Mike D. — the model assumed Mary was the family's emotional-narrative submitter when in fact Mike is.\n\nTwo-week running record: predictions are improving but the framework keeps overestimating how much sentimental context drives votes. Round 3 hypothesis: ignore submitter narratives entirely and predict on song-recognition alone."
        }
    ]
}

COMMENTARY[5] = {
    "title": "Week 5 Recap",
    "sections": [
        {
            "heading": "Deep Cuts Only — and the rule got broken immediately",
            "text": "The first echo-chamber-breaker round asked for an artist with under 50,000 monthly Spotify listeners. The theme mostly worked, but it also produced the season's first wave of caught rule-breakers, and Dray appointed himself the enforcement division.\n\nElyse submitted \"Grey Luh,\" a song with nearly 100 million streams, and Dray's zero-point comment did not hold back: \"Wow, submitting a song with almost 100,000,000 streams. A real deep cut! Couldn't have just waited until new discoveries week next week?\" Cindy E., playing her very first round, also overshot the cap, and Dray hit her with \"I was going to vote for you, but you cheated. Do you understand how numbers work?\" Welcome to the family, Cindy. Meanwhile the players who actually dug deep flexed it in their notes: Mike D. proudly flagged his Podipto pick at \"294 monthly listeners!?\" and his Will Ingram pick at \"4785 monthly listeners,\" and Dray crowned Gabriel's \"Desmancha\" the winner of \"deepest cut lol.\""
        },
        {
            "heading": "Claire E. wins again — Mills had the top song, but Claire had the better round",
            "text": "Here's the distinction that decides the round: Mills T. submitted the single highest-scoring song of the week, \"Louisiana Saturday Night\" by the Benjy Davis Project (11 points), which Mills tagged \"SEC legends.\" But a Music League round is won on combined two-song total, and there Claire E. took it with 19 points: \"High Feeling\" (10 pts, which she called \"Melodic Cosmic country - The Band - Americana sensation\") plus \"Lose My Number\" (9 pts, \"Grit and groove\"). Mills's 15-point total tied him for second with Jack L., who also banked 15.\n\nSo Mills wins Song of the Week and Claire wins the round, her second victory of the season after World Music Week. The round distributed 100 points across the playlist in a wide, healthy spread, which is exactly what a discovery format should produce: lots of songs catching a few votes each rather than everyone piling onto one known quantity."
        },
        {
            "heading": "Cindy E. joins the league",
            "text": "Round 5 marks the debut of Cindy E., the twelfth player, who submitted two songs (\"Lovable Girl\" and \"Your Best Friend\"), voted, and apart from the monthly-listener miscalculation jumped straight into the fray. \"Lovable Girl\" pulled 4 points; \"Your Best Friend\" was the round's only zero. A modest debut on the scoreboard, but she is officially on the board and on the site as of this week."
        },
        {
            "heading": "Standings after five",
            "text": "Claire E. extended her lead to 77 points, well ahead of the field, and her Round 5 win makes her the season's first two-time round winner. The discovery format scrambled the middle a bit, but the top of the table stayed remarkably stable, which is becoming the season's defining feature: Claire is consistent, everyone else is volatile. Through five rounds there have been five round victories spread across four people: Olivia, Mills, Mary, and Claire twice."
        }
    ]
}

COMMENTARY[6] = {
    "title": "Week 6 Recap",
    "sections": [
        {
            "heading": "Fresh Finds — the lowest-scoring round of the season",
            "text": "The \"discovered in the last 60 days\" round produced the thinnest scoreboard yet: just 70 total points, well below the ~100 of a healthy round. The reason is structural and a little telling. Four players forfeited by not voting (Olivia, Gabriel, Steve, and new arrival Cindy), so a third of the league's voting power simply didn't show up. Fewer voters means fewer points to distribute, and the whole board compresses.\n\nThis is the echo-chamber experiment's most ambiguous result. When everyone was forced to bring something genuinely new, engagement actually dropped. Genuine discovery is harder work than reaching for the family canon, and the participation reflected it."
        },
        {
            "heading": "Dray E. wins his second round with a Swamp Dogg deep cut",
            "text": "Dray took Round 6 at 8 points with \"Creeping Away\" by Swamp Dogg, attaching a full artist bio: \"Swamp Dogg is the alter ego of Jerry Williams Jr., a soul singer-songwriter and producer who adopted the persona in 1970 to make music exactly as weird and uncompromising as he wanted... decades later he's been embraced by indie artists like Bon Iver and Justin Vernon.\" His second submission, the Anri city-pop track \"悲しみがとまらない (I Can't Stop the Loneliness),\" tied for fifth at 5 points with another deep-dive note about Japan's 1980s economic-boom soundtrack. The man does his homework, and the votes followed.\n\nOlivia's \"Mr. Saturday Night\" and Gabriel's \"When I'm Stoned\" both pulled 6 raw points, enough to place high, but both were zeroed by forfeit since neither voted."
        },
        {
            "heading": "Claire follows her own rules, loudly",
            "text": "Claire's vote comments this round read like a one-woman narration. On her own \"Mama's Sunshine, Daddy's Rain\" she wrote: \"Okay.. the band isn't new.. but I haven't heard this song and I love it!! Sorry not sorry, dray. I followed the rules and did explore tons of music.\" That is a preemptive defense aimed directly at the league's self-appointed rule enforcer. On Tess's \"The Returner\" she gave 2 points with \"Almost submitted Allison myself!!!\" Tess, for her part, described that same song as making her \"feel good about myself!!!!! The lyrics are so gewd.\" Claire scored 8 in the round and held her overall lead comfortably."
        },
        {
            "heading": "Standings after six",
            "text": "Claire E. remained the runaway leader. The forfeit-heavy round meant several players banked nothing: Olivia, Gabriel, Steve, and Cindy all took zeros, which stretched Claire's cushion further. Six rounds in, the season frontrunner has gone the entire run without a single bad week. The chasing pack of Mills, Dray, and Jack stayed within range of each other but lost ground to the leader."
        }
    ]
}

COMMENTARY[7] = {
    "title": "Week 7 Recap",
    "sections": [
        {
            "heading": "Scouting Report (written blind)",
            "text": "The blind report was committed before votes were revealed, submitter IDs stripped. Top 5 prediction: James Bond Theme (Song of the Week pick), Dean Town, Nutcracker Pas de Deux, Dawn from Pride & Prejudice, and Axel F. The report flagged two theme-breakers to watch — Sonnentanz \"Sun Don't Shine\" (the vocal version of an otherwise-instrumental track) and Walk Faster — and predicted the Clair de Lune collision, two players submitting the same Debussy piece. Full scorecard at the bottom."
        },
        {
            "heading": "Steve E. wins his first round with smooth-jazz flugelhorn",
            "text": "Steve E. took No Words at 9 points with \"Feels So Good\" by Chuck Mangione, the 1977 flugelhorn hit, and it drew the broadest support of the round at 8 voters. Dray's vote comment hinted at the origin: \"Did the king of the hill wd40 link I sent seed this idea? That Chuck Mangione is one class act!\" — a callback to a King of the Hill clip that had been circulating in the family thread. Steve's other submission, Axel F (the Beverly Hills Cop theme), added 6 more for a 15-point round.\n\nThe top was a near-deadlock: Feels So Good (9) edged a four-way logjam at 8 points — Dean Town (Dray), Dern Kala (Mills), Jeep On 35 (Claire), and Chariots of Fire (Cindy). One point separated first from fifth, the tightest top of any round this season."
        },
        {
            "heading": "The theme-breaker prediction landed: Elyse's Sonnentanz takes the only zero",
            "text": "The blind report flagged Sonnentanz \"Sun Don't Shine\" as a vocal track sneaking into a no-words round, predicting it would be punished if caught. It was caught, and punished: the song was the round's only zero, submitted by Elyse E. Dray's zero-point comment was blunt — \"What part of no words wasn't clear?\" — and Claire piled on with a one-word \"Words..?\" This is the second straight discovery round in which Elyse has had a submission flagged for breaking the prompt; in Week 5 her \"Grey Luh\" was far too popular for a Deep Cuts round.\n\nCindy nearly took a second zero for the same reason. Her \"Suicide Is Painless\" (the M*A*S*H theme) was submitted in a version with lyrics. Mary's vote comment: \"I'm hearing lotsa words words words.\" Claire's: \"So many so many so many words.\" Dray was more forgiving — \"That's a lot of words, I believe they used the instrumental version for the show\" — and the song scraped a single point."
        },
        {
            "heading": "The Clair de Lune collision was the Dillon parents",
            "text": "The blind report predicted two independent Clair de Lune submissions would split the vote and both miss the top tier. Confirmed, and the twist is that both came from the Dillon parents. Mary's Clair de Lune scored 3 points; Mike's scored 1. Mike leaned all the way in: \"Have to go here; especially after retitling as Clair de Lune Ensor.\" Caught between her parents, Claire gave Mike a single point with \"Had to give only one vote to one of 'my songs.'\" Mary, noticing the duplicate mid-vote, wrote \"Dang we have two!!\" The collision suppressed both exactly as predicted; neither cracked the top ten."
        },
        {
            "heading": "Did No Words break the echo chamber? Partly",
            "text": "Stripping out the lyrics flattened the scoreboard in a revealing way. The round distributed 100 points but the top was a five-way near-tie (9-8-8-8-8) rather than a clear runaway. The funk and groove picks did conspicuously well — Dean Town, Dern Kala, MRG, and Jeep On 35 all landed in the top six — which suggests that with no words to lean on, the family rewarded feel and craft. Meanwhile the recognizable film and classical cues underperformed expectations: the Nutcracker finished 16th and the James Bond Theme 7th, both well below where name recognition alone would have put them. Take away the words and this family votes more on how a song feels and less on whether they already know it, which is exactly what this three-round experiment was hoping to surface."
        },
        {
            "heading": "Standings after seven",
            "text": "Claire E. leads the season at 96 points, now 18 clear of Mills T. (78), with Dray E. third (73) and Jack L. fourth (65). Claire has placed in the upper tier all seven rounds and remains the only player without a single bad week, a genuinely dominant run. Steve's win lifts him out of the basement. Cindy sits twelfth at 13 points across her three active rounds. Seven rounds in, Claire is no longer just the frontrunner; barring a collapse, she is the clear favorite to take the season."
        },
        {
            "heading": "Blind report scorecard",
            "text": "Top 5 prediction versus actual: Dean Town predicted #2, finished #3 (8 pts), the best call, within one. Axel F predicted #5, finished #8 (6 pts), within three. James Bond Theme predicted #1, finished #7 (7 pts), a clear overestimate. Dawn predicted #4, finished #14 (3 pts), a miss. Nutcracker predicted #3, finished #16 (3 pts), the worst miss; the classical and film-score recognizability bet did not pay off. The winner, Feels So Good, was tagged only at 6 to 11 points, not as the favorite.\n\nWhere the report nailed it: the Sonnentanz theme-breaker (predicted lowest or zero, finished dead last at 0), the Clair de Lune vote-split (both suppressed, neither top ten), and Walk Faster being fine (it scored 6 and turns out to be instrumental). Where it whiffed: badly overrating recognizable classical and film cues. The cumulative pattern across seven rounds is now ironclad: this model overvalues songs that are famous and undervalues songs that are good, because this family rewards the latter. Adjustment going forward: weight craft and groove over name recognition, and never again assume the most recognizable submission wins."
        }
    ]
}

COMMENTARY[8] = {
    "title": "Week 8 Recap",
    "sections": [
        {
            "heading": "Scouting Report (written blind)",
            "text": "The blind report was committed before votes were revealed, submitter IDs stripped. Top 5 prediction: Don't Think Twice It's Alright (Song of the Week pick), Gin and Juice, Respect, Killing Me Softly, Rich Girl. The central thesis: the three canonical famous covers — Whitney's \"I Will Always Love You,\" Aretha's \"Respect,\" Tina's \"Proud Mary,\" all more famous than their originals — would all score respectably but none would win, because this family rewards reinvention over recognition. Scorecard at the bottom."
        },
        {
            "heading": "Mary D. wins again — her second round of the season",
            "text": "Mary D. took Covers with 17 points across two of the most famous covers ever recorded: Rufus Wainwright's \"Hallelujah\" (9 points) and Whitney Houston's \"I Will Always Love You\" (8 points). It's her second round win after the Spotify Wrapped round in Week 4, making her one of only two players — alongside Claire — to win multiple rounds this season.\n\nWhat's striking is that Mary won by leaning hard into the famous-cover strategy that the blind report bet against, and made it work through sheer song quality plus genuinely good liner notes. On Whitney she wrote: \"Dolly wrote it and sang it well but Whitney changed it forever.\" On Hallelujah: \"So many good covers of this song. K.D. Lang and Jeff Buckley versions were amazing but this one is tied to Shrek all time great kiddie movie for grown ups.\" Mary knows exactly what she submitted and why, and the voters rewarded the conviction."
        },
        {
            "heading": "Claire had the single best song — and her daughter's stamp of approval",
            "text": "Claire E. finished second in the round at 14 points but submitted the highest-scoring single song of the week: Lake Street Dive's soul cover of Hall & Oates' \"Rich Girl\" (11 points, 7 voters), narrowly the most democratic pick of the round. Her submitter comment revealed the real judge: \"Ella was born to this one :) lol.\" Claire's daughter Ella gets a recurring role in this round — Claire also noted she \"blasted Ella with this song on the way home one day this week\" when voting for her mother's Whitney cover. Three generations of Dillon women in one round: Mary submitting, Claire voting, Ella reacting from the car seat.\n\nClaire remains the runaway season leader and her near-win keeps her perfect record intact: she has finished in the upper half of every single round across all eight weeks."
        },
        {
            "heading": "The famous-cover thesis held: all three icons scored, none won",
            "text": "The blind report's central bet was that Whitney, Aretha, and Tina would all be undeniable but none would take the round, because this family prefers a surprising reinvention to a canonical performance. The verdict: Whitney's \"I Will Always Love You\" finished 4th (8 pts), Tina's \"Proud Mary\" 12th (5 pts), and Aretha's \"Respect\" 15th (4 pts). All three scored, none won, exactly as predicted — though the model badly overrated Respect, which it had pegged at #3.\n\nThe winning move instead came from the family's actual native dialect: soulful, string-band, and jam-adjacent reinventions. The top of the board was Lake Street Dive's soul (Rich Girl), Rufus Wainwright's theatrical Hallelujah, and The Gourds' legendary bluegrass \"Gin and Juice\" (Mills, 3rd at 8 points) — the cover of Snoop Dogg that this family was always going to love. Steve's Proud Mary did draw the round's best comment, from Claire: \"I will dance my ass off to this song at every wedding.\""
        },
        {
            "heading": "Dray's voting comments were a one-man comedy set",
            "text": "Dray spread the standard ten 1-point votes across ten songs again, but the comments attached to them were the real event. On Steve's Proud Mary (which he gave 0): \"a tape deck, some Creedence tapes, and there was a, uh... my briefcase.\" On Jack's Little Feat cover: \"I'm a little feat slut and I don't care who knows it.\" On Claire's Pepper: \"I knew this would be here, it was on my short list for pandering purposes.\" On Mike's Susan Tedeschi cover: \"Hello fellow Susan enjoyer.\" He also revealed that three other songs (Where Is My Mind, Rocky Raccoon, and Two Trains) had all been on his own short list, which is either taste alignment or mild competitive frustration, hard to say which.\n\nNotably, Susan Tedeschi appeared twice this round — on Dray's own \"Don't Think Twice\" (as featured vocalist) and Mike's \"You Got The Silver\" — but from two different submitters, not one superfan, with Dray saluting Mike as a \"fellow Susan enjoyer.\""
        },
        {
            "heading": "Standings: Claire pulls toward an insurmountable lead",
            "text": "Claire E. now leads the season at 110 points, 20 clear of Mills T. (90), with Dray E. third (83) and Jack L. fourth (75). Mary's win moves her into a tie for fifth with Mike at 64. The story at the top is no longer in much doubt: Claire has now placed in the upper half of all eight rounds, the only player who can claim that, and with two rounds banked at 18 and 19 points she has both the highest ceiling and the steadiest floor in the league.\n\nJack L. holds an unusual distinction — fourth in the season at 75 points without a single round win, the best player yet to take a weekly trophy. Six different players have now won rounds (Olivia, Mills, Claire twice, Mary twice, Dray, Steve), but Claire is the one pulling away from the pack."
        },
        {
            "heading": "Blind report scorecard",
            "text": "Top 5 prediction versus actual: Rich Girl predicted #5, finished #1 (11 pts) — the model correctly tagged it a sleeper top-five and undersold how good it was. Gin and Juice predicted #2, finished #3 (8 pts), within one. Killing Me Softly predicted #4, finished #8 (6 pts), within four. Don't Think Twice (the Song of the Week pick) predicted #1, finished #6 (7 pts) — an overestimate, but still near the top. Respect predicted #3, finished #15 (4 pts) — the worst miss; the model wildly overrated Aretha's recognition value, which is the exact mistake it has made all season.\n\nWhere the report nailed it: the famous-cover thesis (Whitney, Tina, and Aretha all scored, none won — precisely the predicted pattern), two of three bottom predictions (Hotel California 23rd, Maggie May 22nd), and the Susan Tedeschi double-appearance (though they turned out to be two submitters, which the report hedged). Where it whiffed: overrating canonical recognition again, this time on Aretha. Eight rounds in, the lesson is now permanent — in this family, being the most famous version is worth less than being the most delightful one. The model's job going forward is to stop being impressed by songs everyone already knows."
        }
    ]
}

COMMENTARY[9] = {
    "title": "Week 9 Recap",
    "sections": [
        {
            "heading": "The most personal prompt produced the least decisive result",
            "text": "Closer entrance music asks for the single most individual choice in baseball: the ninety seconds that are supposed to be uniquely yours. Across the season's other eight rounds, a clear winner always separated from the pack — the best song beat the second-best by an average of two points, and twice by six. Round 9 is the only round all season where the top two songs finished dead even. Mike D.'s Dirty Deeds Done Dirt Cheap and Olivia D.'s X Gon' Give It To Ya both landed on 11, and behind them Crazy Train and I'm Shipping Up To Boston both landed on 9. The top four read 11-11-9-9, the flattest leaderboard the family has ever produced.\n\nAnd it wasn't because nobody cared. The opposite: the round drew six maximum three-point votes, tied for the second-most conviction of any round this season, and 27 of 28 songs scored at least a point, the highest participation rate all year. Everyone voted hard. They just voted hard in different directions. The prompt that was supposed to surface one defining anthem instead revealed that twelve people's idea of intimidation points twelve different ways — which is its own kind of answer."
        },
        {
            "heading": "The family brought rap and then voted for guitars",
            "text": "This was, by a wide margin, the most hip-hop the family has ever submitted: 11 of the 28 songs were rap, in a league whose center of gravity is jam bands and Americana. It looked like a genre coming out party. Then the votes landed, and the top four were AC/DC, DMX, Ozzy Osbourne, and the Dropkick Murphys — three classic-rock and one Celtic-punk anthem, with DMX's X Gon' Give It To Ya the lone rap song to crack the top tier, sitting at number two.\n\nThe split is sharper under the hood. The 11 rap songs averaged 5.6 points each; the 8 rock songs averaged 5.8 — functionally identical. Rap didn't get rejected; it got distributed. The family spread its rap votes evenly across a dozen tracks and then concentrated its rock votes onto a few anthems, so every one of the round's peaks came with a guitar. When this family wants a song to *win*, nine rounds of data now say it reaches for a riff."
        },
        {
            "heading": "Cindy E. climbed out of the basement and tied for the win",
            "text": "Cindy joined in Round 5 and spent four weeks at the bottom of the league. Her round-by-round finishing positions tell the whole story: ninth, twelfth, sixth, twelfth. She was, by the numbers, the least competitive player in the family — twice finishing dead last — the grandmother who famously miscalculated her monthly-listener counts in the Deep Cuts round and got publicly scolded for it.\n\nIn Round 9 she finished second of fourteen, on 16 points, and tied Olivia D. for the round win — the first co-championship in league history. Both reached 16: Olivia on X Gon' Give It To Ya plus Move Bitch, Cindy on Crazy Train plus All I Do Is Win, two stadium anthems played without a trace of irony. Four rounds in the cellar, then a flawless reading of the one prompt that rewarded exactly what she brought. Closer music, it turns out, was Cindy's game all along."
        },
        {
            "heading": "Steve E. didn't just vote for the co-champion — he built her",
            "text": "Cindy won the round by a margin of zero, which makes the question of who supplied her points more than academic. The answer is Steve E. Of the ten points Steve had to give, he put six on Cindy: a maximum three on All I Do Is Win and another maximum three on Crazy Train. His only other meaningful vote, a third three, went to Mike's Dirty Deeds — the song that tied for first overall. Steve spent his entire allotment of conviction on the two songs that finished at the very top of the board, and one of them was lifted into a tie for the win almost single-handedly by his support. In a round decided by nothing, the kingmaker had a name and a receipt."
        },
        {
            "heading": "Claire E. had her worst round of the season and her lead grew anyway",
            "text": "Claire finished sixth in Round 9. That is, by a comfortable distance, the lowest she has placed all season — she had finished outside the top four exactly once before, a fifth in Round 2, and otherwise lived in the top three. And her lead over the field went *up*.\n\nThat sentence is the entire Claire E. season in miniature. She took over first place after Round 2 and has never given it back, and the remarkable part is the shape of the margin: 1, then 10, 12, 16, 19, 18, 20, 21. Almost monotonic growth over seven straight rounds, built not on explosive weeks but on the simple refusal to ever have a genuinely bad one. In nine rounds she has finished first twice, second three times, and never lower than sixth; in Round 9 she posted that sixth and still stretched her cushion to 21 points, because a merely-okay Claire week is still better than everyone else's average. With two rounds left, the math is nearly settled — not because she keeps winning, but because she never loses ground."
        },
        {
            "heading": "Jack L., the best player who cannot win a round",
            "text": "Jack L. sits fourth in the season standings on 83 points, ahead of two players who have each won a round outright and several who have come close. He has not won a round. He has, in fact, never finished higher than third in any single week — a mark he reached twice, in Rounds 5 and 6, always close enough to see the summit and never close enough to touch it.\n\nIt is one of the quietly remarkable lines in the data: nine rounds of steady upper-table finishes that have added up to the fourth-most points in the league and exactly zero trophies. Jack is the family's most reliable non-winner, the player whose floor is high enough to contend for the season and whose ceiling has, so far, topped out at least one spot short every single time. Two rounds remain for the pattern to break — or to become the defining stat of his season."
        },
        {
            "heading": "The cousins arrive into a fourteen-person field",
            "text": "Claire's cousins Jake H. and Kelsey H. became the 13th and 14th players this week, the largest the league has ever been. Their debuts split: Kelsey opened with 6 points and a mid-pack finish, while Jake's Every Time I Die metalcore submission became the round's only goose egg — zero points, zero voters, the first shutout since the Covers round. With fourteen players now submitting two songs each, the leaderboard has to distribute the same pool of votes across 28 songs instead of the early season's 20, which is part of why the per-song scores keep compressing: more songs, same fixed conviction, flatter results. The field has nearly doubled since Round 1, and the math of winning a round has quietly gotten harder for everyone in it."
        },
        {
            "heading": "Blind report scorecard, and the rule that finally broke",
            "text": "For eight rounds the prediction model made one consistent error: it overrated famous songs, because this family had spent the whole season punishing the obvious and rewarding the deep cut. So in Round 9 the model bet against the obvious again — and walked directly into the one round where the obvious was the entire point.\n\nThe results: I'm Shipping Up To Boston, predicted third, finished third. Crazy Train, predicted fourth, finished fourth. Two clean hits. But the confident Song of the Week pick, the Kill Bill instrumental Battle Without Honor or Humanity, finished 18th — the worst top-pick miss of the season — and the model's bet that a fresher banger would beat the certified stadium classics was exactly backwards. The four most recognizable songs on the playlist swept the top four. The lesson is the inverse of every prior week: when the prompt is literally 'the song 45,000 people recognize,' recognition stops being a penalty and becomes the assignment. Nine rounds in, the family's one ironclad rule — that the famous pick underperforms — finally met the exception that defined it."
        }
    ]
}


# ---------------------------------------------------------------------------
# Season leaderboard
# ---------------------------------------------------------------------------

def build_season(rounds, joined):
    season = []
    for pid, name in PLAYERS.items():
        join_rd = joined.get(pid)
        if join_rd is None:
            # Player has never been active — still include them at 0 to show on roster
            join_rd = 1
        weekly = []
        total = 0
        wins = 0
        for rd in rounds:
            if rd['number'] < join_rd:
                continue
            entry = next((e for e in rd['leaderboard'] if e['player_id'] == pid), None)
            if entry:
                pts = entry['points']
                rank = entry['rank']
                wins += 1 if rank == 1 and pts > 0 else 0
            else:
                pts = 0
                rank = None
            weekly.append({'round': rd['number'], 'points': pts, 'rank': rank})
            total += pts

        played = len(weekly)
        avg = round(total / played, 1) if played else 0.0
        season.append({
            'player_id': pid,
            'player': name,
            'points': total,
            'rounds_played': played,
            'wins': wins,
            'avg_per_round': avg,
            'joined_round': join_rd,
            'weekly': weekly,
        })

    season.sort(key=lambda e: (-e['points'], -e['avg_per_round'], e['player']))
    rank = 0
    last = None
    for i, e in enumerate(season):
        if e['points'] != last:
            rank = i + 1
            last = e['points']
        e['rank'] = rank
    return season

# ---------------------------------------------------------------------------
# Voting affinities
# ---------------------------------------------------------------------------

def build_voting_affinities(rounds):
    pair_pts = defaultdict(int)
    pair_times = defaultdict(int)
    for rd in rounds:
        for v in rd['vote_details']:
            if v['voter_id'] == v['submitter_id']:
                continue
            key = (v['voter'], v['submitter'])
            pair_pts[key] += v['points']
            pair_times[key] += 1

    affinities = [
        {'voter': v, 'submitter': s, 'total_pts': pts, 'times': pair_times[(v, s)]}
        for (v, s), pts in pair_pts.items()
    ]
    affinities.sort(key=lambda x: -x['total_pts'])
    return affinities

# ---------------------------------------------------------------------------
# Hall of fame
# ---------------------------------------------------------------------------

def build_hall_of_fame(rounds, top_n=20):
    all_songs = []
    for rd in rounds:
        for s in rd['songs']:
            all_songs.append({
                'round': rd['number'],
                'title': s['title'],
                'artist': s['artist'],
                'submitter': s['submitter'],
                'submitter_id': s['submitter_id'],
                'total_pts': s['total_pts'],
                'unique_voters': s['unique_voters'],
                'track_id': s['track_id'],
                'spotify_url': s['spotify_url'],
            })
    all_songs.sort(key=lambda x: (-x['total_pts'], -x['unique_voters']))
    return all_songs[:top_n]

# ---------------------------------------------------------------------------
# Player profiles
# ---------------------------------------------------------------------------

def build_player_profiles(rounds, season):
    season_by_pid = {e['player_id']: e for e in season}
    profiles = {}
    for pid, name in PLAYERS.items():
        submissions = []
        for rd in rounds:
            for s in rd['songs']:
                if s['submitter_id'] == pid:
                    submissions.append({
                        'round': rd['number'],
                        'title': s['title'],
                        'artist': s['artist'],
                        'album': s['album'],
                        'total_pts': s['total_pts'],
                        'unique_voters': s['unique_voters'],
                        'track_id': s['track_id'],
                        'spotify_url': s['spotify_url'],
                    })
        submissions.sort(key=lambda x: (x['round'], -x['total_pts']))

        voting_history = []
        for rd in rounds:
            for v in rd['vote_details']:
                if v['voter_id'] == pid:
                    voting_history.append({
                        'round': rd['number'],
                        'song': v['song'],
                        'voted_for': v['submitter'],
                        'points_given': v['points'],
                    })

        season_entry = season_by_pid.get(pid, {})
        profiles[pid] = {
            'name': name,
            'submissions': submissions,
            'voting_history': voting_history,
            'season_points': season_entry.get('points', 0),
            'rounds_played': season_entry.get('rounds_played', 0),
        }
    return profiles

# ---------------------------------------------------------------------------
# Fun metrics
# ---------------------------------------------------------------------------

def build_fun_metrics(rounds, season):
    # Kingmaker
    kingmaker_pts = defaultdict(int)
    kingmaker_detail = defaultdict(list)
    for rd in rounds:
        if not rd['songs']:
            continue
        winner = rd['songs'][0]
        for v in rd['vote_details']:
            if v['submitter_id'] == winner['submitter_id'] and v['song'] == winner['title']:
                kingmaker_pts[v['voter_id']] += v['points']
                kingmaker_detail[v['voter_id']].append(f"R{rd['number']}: {v['points']} pts to {winner['title']}")
    if kingmaker_pts:
        top_pid, top_pts = max(kingmaker_pts.items(), key=lambda x: x[1])
        kingmaker = {
            'title': 'Kingmaker',
            'description': 'Most points given to eventual weekly winners',
            'leader': {
                'player': display(top_pid),
                'value': f'{top_pts} pts',
                'detail': ' · '.join(kingmaker_detail[top_pid]),
            }
        }
    else:
        kingmaker = {'title': 'Kingmaker', 'description': 'No data yet', 'leader': {}}

    # ------------------------------------------------------------------
    # The Spreader vs The Sniper — voting concentration personality
    # Spreader: most songs voted per round (egalitarian). Sniper: fewest
    # songs per round paired with the highest average max-vote (all-in).
    # ------------------------------------------------------------------
    voter_round_spread = defaultdict(list)   # pid -> [songs voted each round]
    voter_round_max = defaultdict(list)      # pid -> [max single vote each round]
    voter_threes = defaultdict(int)
    for rd in rounds:
        by_voter = defaultdict(list)
        for v in rd['vote_details']:
            if v['points'] > 0:   # exclude zero-point rows — those are comments, not votes
                by_voter[v['voter_id']].append(v['points'])
        for pid, pl in by_voter.items():
            if not pl:
                continue
            voter_round_spread[pid].append(len(pl))
            voter_round_max[pid].append(max(pl))
            voter_threes[pid] += sum(1 for x in pl if x == 3)
    eligible = [p for p in voter_round_spread if len(voter_round_spread[p]) >= 3]
    voting_style = {'title': 'Spreader vs. Sniper', 'description': 'Who spreads their ten points thin, and who saves them for a knockout', 'spreader': {}, 'sniper': {}}
    if eligible:
        spreader_pid = max(eligible, key=lambda p: sum(voter_round_spread[p]) / len(voter_round_spread[p]))
        sp_avg = sum(voter_round_spread[spreader_pid]) / len(voter_round_spread[spreader_pid])
        # Sniper: highest avg max-vote, tiebreak fewest songs/round
        sniper_pid = max(eligible, key=lambda p: (sum(voter_round_max[p]) / len(voter_round_max[p]), -sum(voter_round_spread[p]) / len(voter_round_spread[p])))
        sn_spread = sum(voter_round_spread[sniper_pid]) / len(voter_round_spread[sniper_pid])
        sn_max = sum(voter_round_max[sniper_pid]) / len(voter_round_max[sniper_pid])
        voting_style['spreader'] = {'player': display(spreader_pid), 'value': f'{sp_avg:.1f} songs/round, {voter_threes[spreader_pid]} max votes'}
        voting_style['sniper'] = {'player': display(sniper_pid), 'value': f'{sn_spread:.1f} songs/round, {voter_threes[sniper_pid]} max votes'}

    # ------------------------------------------------------------------
    # Front-Runner vs Lone Wolf — does your favorite agree with the room?
    # For each round, take the song the voter gave the most points to and
    # find where it finished (percentile). Average across rounds.
    # Front-runner = lowest avg percentile (backs winners). Lone wolf =
    # highest (favorites finish near the bottom).
    # ------------------------------------------------------------------
    voter_fav_pct = defaultdict(list)
    for rd in rounds:
        n = len(rd['songs'])
        if n == 0:
            continue
        rank = {(s['title'], s['submitter_id']): i + 1 for i, s in enumerate(rd['songs'])}
        by_voter = defaultdict(list)
        for v in rd['vote_details']:
            by_voter[v['voter_id']].append((v['points'], v['song'], v['submitter_id']))
        for pid, picks in by_voter.items():
            mx = max(p for p, _, _ in picks)
            favs = [(s, sub) for p, s, sub in picks if p == mx]
            for s, sub in favs:
                rk = rank.get((s, sub))
                if rk:
                    voter_fav_pct[pid].append(rk / n)
    elig2 = [p for p in voter_fav_pct if len(voter_fav_pct[p]) >= 5]
    allegiance = {'title': 'Front-runner vs. Lone wolf', 'description': 'Whether the song you back hardest each week tends to win the room or stand alone', 'front_runner': {}, 'lone_wolf': {}}
    if elig2:
        fr_pid = min(elig2, key=lambda p: sum(voter_fav_pct[p]) / len(voter_fav_pct[p]))
        lw_pid = max(elig2, key=lambda p: sum(voter_fav_pct[p]) / len(voter_fav_pct[p]))
        fr_avg = sum(voter_fav_pct[fr_pid]) / len(voter_fav_pct[fr_pid])
        lw_avg = sum(voter_fav_pct[lw_pid]) / len(voter_fav_pct[lw_pid])
        allegiance['front_runner'] = {'player': display(fr_pid), 'value': f'favorite finishes ~{fr_avg*100:.0f}th %ile'}
        allegiance['lone_wolf'] = {'player': display(lw_pid), 'value': f'favorite finishes ~{lw_avg*100:.0f}th %ile'}

    # ------------------------------------------------------------------
    # The Closer — most submissions that finished top-3 in their round.
    # Rewards consistently bringing heat, not one big week.
    # ------------------------------------------------------------------
    top3_counts = defaultdict(int)
    top3_detail = defaultdict(list)
    for rd in rounds:
        for i, s in enumerate(rd['songs'][:3]):
            if s['total_pts'] > 0:
                top3_counts[s['submitter_id']] += 1
                top3_detail[s['submitter_id']].append(rd['number'])
    closer_sorted = sorted(top3_counts.items(), key=lambda x: (-x[1], display(x[0])))
    closer = {
        'title': 'The Closer',
        'description': 'Most songs that finished top three in their round — week-in, week-out heat',
        'leaders': [
            {'player': display(pid), 'value': f'{n} top-3 finishes'}
            for pid, n in closer_sorted[:5] if n > 0
        ]
    }

    # ------------------------------------------------------------------
    # Patron & Beneficiary — biggest one-way point flows across the season.
    # ------------------------------------------------------------------
    flow = defaultdict(int)
    for rd in rounds:
        for v in rd['vote_details']:
            if v['voter_id'] != v['submitter_id']:
                flow[(v['voter_id'], v['submitter_id'])] += v['points']
    flow_sorted = sorted(flow.items(), key=lambda x: -x[1])
    patronage = {
        'title': 'Patron & Beneficiary',
        'description': 'The most generous one-way streets — who keeps funding whom',
        'flows': [
            {'from': display(a), 'to': display(b), 'value': f'{pts} pts'}
            for (a, b), pts in flow_sorted[:5]
        ]
    }

    # ------------------------------------------------------------------
    # Best Friends & Cold Shoulders — strongest and weakest two-way bonds
    # (combined points exchanged), among players with enough shared rounds.
    # ------------------------------------------------------------------
    mutual = defaultdict(int)
    for (a, b), pts in flow.items():
        mutual[tuple(sorted([a, b]))] += pts
    # tenure: rounds in which a player voted
    tenure = defaultdict(int)
    for rd in rounds:
        for pid in set(v['voter_id'] for v in rd['vote_details']):
            tenure[pid] += 1
    longtimers = [p for p in PLAYERS if tenure[p] >= 7]
    pair_list = []
    for i, a in enumerate(longtimers):
        for b in longtimers[i+1:]:
            pair_list.append((a, b, mutual[tuple(sorted([a, b]))]))
    best_pair = max(pair_list, key=lambda x: x[2]) if pair_list else None
    cold_sorted = sorted(pair_list, key=lambda x: x[2])[:3]
    bonds_rows = []
    if best_pair:
        bonds_rows.append({'pair': f'{display(best_pair[0])} & {display(best_pair[1])}', 'value': f'{best_pair[2]} pts · closest'})
    for a, b, pts in cold_sorted:
        bonds_rows.append({'pair': f'{display(a)} & {display(b)}', 'value': f'{pts} pts · coldest'})
    bonds = {
        'title': 'Best friends & cold shoulders',
        'description': 'The tightest mutual bond in the family, and the frostiest',
        'rows': bonds_rows
    }

    return {
        'kingmaker': kingmaker,
        'voting_style': voting_style,
        'allegiance': allegiance,
        'closer': closer,
        'patronage': patronage,
        'bonds': bonds,
    }

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    rounds_csv, subs, votes = load_csvs()
    joined = compute_join_rounds(subs, votes)
    rounds = build_rounds(rounds_csv, subs, votes)

    for rd in rounds:
        if rd['number'] in COMMENTARY:
            rd['commentary'] = COMMENTARY[rd['number']]

    season = build_season(rounds, joined)
    affinities = build_voting_affinities(rounds)
    hof = build_hall_of_fame(rounds)
    profiles = build_player_profiles(rounds, season)
    metrics = build_fun_metrics(rounds, season)

    out = {
        'league': {
            'name': 'Fam Music League',
            'subtitle': 'Season One',
            'total_rounds': len(rounds),
        },
        'players': PLAYERS,
        'rounds': rounds,
        'season_leaderboard': season,
        'voting_affinities': affinities[:50],
        'hall_of_fame': hof,
        'player_profiles': profiles,
        'fun_metrics': metrics,
    }

    with open(OUTPUT_PATH, 'w') as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f'Wrote {OUTPUT_PATH}')
    print(f'Rounds: {len(rounds)}')
    for rd in rounds:
        if rd['songs']:
            w = rd['songs'][0]
            print(f"  R{rd['number']} ({rd['name'][:40]}): {len(rd['songs'])} songs, {rd['stats']['total_votes']} votes, winner = {w['title']} ({w['total_pts']} pts, {w['submitter']})")
    print(f'\nSeason top 5:')
    for e in season[:5]:
        print(f"  {e['rank']}. {e['player']} — {e['points']} pts ({e['rounds_played']} rds, {e['wins']} win{'s' if e['wins'] != 1 else ''})")


if __name__ == '__main__':
    main()
