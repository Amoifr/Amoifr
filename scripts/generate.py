#!/usr/bin/env python3
"""Generate the profile README from the pull requests of the user."""

import html
import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

LOGIN = 'Amoifr'
EXCLUDED_OWNERS = {LOGIN, 'PrestaShop'}
TOP_ORGS = 8
OTHER_ORGS = 16
RECENT_PRS = 6
RECENT_RELEASES = 8
HIGHLIGHTED = ['symfony/symfony', 'sulu/sulu']
HIGHLIGHTED_RELEASES = 5

QUERY = '''
query($q: String!, $after: String) {
  search(query: $q, type: ISSUE, first: 100, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        title url number state merged createdAt mergedAt baseRefName
        repository {
          nameWithOwner url description isPrivate
          owner { login avatarUrl url ... on Organization { name } ... on User { name } }
          latestRelease { tagName url publishedAt }
        }
      }
    }
  }
}
'''

RELEASES_QUERY = '''
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    nameWithOwner url
    owner { login avatarUrl url ... on Organization { name } }
    releases(first: 100, orderBy: {field: CREATED_AT, direction: DESC}) {
      nodes { tagName url publishedAt }
    }
  }
}
'''


def graphql(token, variables, query=QUERY):
    request = urllib.request.Request(
        'https://api.github.com/graphql',
        data=json.dumps({'query': query, 'variables': variables}).encode(),
        headers={'Authorization': 'bearer ' + token, 'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(request) as response:
        payload = json.load(response)
    if 'errors' in payload:
        sys.exit(json.dumps(payload['errors']))
    return payload['data']['search'] if query == QUERY else payload['data']


def fetch_pull_requests(token):
    pull_requests = []
    # The search API stops at 1000 results, so the query is split by year
    for year in range(2017, datetime.now(timezone.utc).year + 1):
        after = None
        while True:
            search = graphql(token, {
                'q': f'author:{LOGIN} is:pr created:{year}-01-01..{year}-12-31',
                'after': after,
            })
            pull_requests += [node for node in search['nodes'] if node]
            if not search['pageInfo']['hasNextPage']:
                break
            after = search['pageInfo']['endCursor']
    return [pr for pr in pull_requests if not pr['repository']['isPrivate']]


def fetch_repositories(token):
    repositories = []
    for name_with_owner in HIGHLIGHTED:
        owner, name = name_with_owner.split('/')
        repositories.append(graphql(token, {'owner': owner, 'name': name}, RELEASES_QUERY)['repository'])
    return repositories


def shipped_in(pr, releases):
    """Return the first release of the base branch of the pull request published after its merge."""
    prefix = pr['baseRefName'] + '.'
    candidates = [
        release for release in releases
        if release['tagName'].lstrip('v').startswith(prefix) and release['publishedAt'] > pr['mergedAt']
    ]
    return min(candidates, key=lambda release: release['publishedAt']) if candidates else None


def ago(date):
    days = (datetime.now(timezone.utc) - datetime.fromisoformat(date.replace('Z', '+00:00'))).days
    if days == 0:
        return "aujourd'hui"
    if days == 1:
        return 'hier'
    if days < 30:
        return f'il y a {days} jours'
    if days < 365:
        return f'il y a {days // 30} mois'
    return f'il y a {days // 365} an' + ('s' if days >= 730 else '')


def avatar(owner, size):
    return owner['avatarUrl'] + ('&' if '?' in owner['avatarUrl'] else '?') + f's={size * 2}'


def render(pull_requests, repositories):
    contributions = [pr for pr in pull_requests if pr['repository']['owner']['login'] not in EXCLUDED_OWNERS]
    merged = [pr for pr in contributions if pr['merged']]

    orgs = defaultdict(lambda: {'merged': 0, 'repos': defaultdict(int)})
    for pr in merged:
        owner = pr['repository']['owner']
        org = orgs[owner['login']]
        org['owner'] = owner
        org['merged'] += 1
        org['repos'][pr['repository']['nameWithOwner'].split('/')[1]] += 1
    ranking = sorted(orgs.values(), key=lambda org: -org['merged'])

    lines = [
        '<h2 align="center">Salut, moi c\'est Pascal 👋</h2>',
        '',
        '<p align="center">Développeur PHP. Je contribue surtout à l\'écosystème Symfony et à Sulu,<br>',
        'un correctif à la fois, sur mon temps libre.</p>',
        '',
        '<p align="center">',
        f'  <img src="https://img.shields.io/badge/PR_mergées-{len(merged)}-8957e5?style=for-the-badge" alt="{len(merged)} PR mergées">',
        f'  <img src="https://img.shields.io/badge/projets-{len({pr["repository"]["nameWithOwner"] for pr in merged})}-1f6feb?style=for-the-badge" alt="projets">',
        f'  <img src="https://img.shields.io/badge/organisations-{len(orgs)}-238636?style=for-the-badge" alt="organisations">',
        '</p>',
        '',
        '### 🏆 Là où je contribue le plus',
        '',
        '<table>',
    ]

    top = ranking[:TOP_ORGS]
    for row in range(0, len(top), 4):
        lines.append('  <tr>')
        for org in top[row:row + 4]:
            owner = org['owner']
            repos = sorted(org['repos'].items(), key=lambda item: -item[1])[:3]
            lines += [
                '    <td align="center" width="25%">',
                f'      <a href="{owner["url"]}"><img src="{avatar(owner, 64)}" width="64" height="64" alt="{owner["login"]}"></a><br>',
                f'      <b>{html.escape(owner.get("name") or owner["login"])}</b><br>',
                f'      <sub><b>{org["merged"]}</b> PR mergée{"s" if org["merged"] > 1 else ""}</sub><br>',
                '      <sub>' + ' · '.join(
                    f'<a href="{owner["url"]}/{repo}">{repo}</a>' for repo, _ in repos
                ) + '</sub>',
                '    </td>',
            ]
        lines.append('  </tr>')
    lines += ['</table>', '']

    others = ranking[TOP_ORGS:TOP_ORGS + OTHER_ORGS]
    if others:
        lines.append('<p>Et aussi :')
        for org in others:
            owner = org['owner']
            title = f'{owner["login"]} : {org["merged"]} PR mergée' + ('s' if org['merged'] > 1 else '')
            lines.append(f'  <a href="{owner["url"]}"><img src="{avatar(owner, 28)}" width="28" height="28" '
                         f'alt="{owner["login"]}" title="{title}"></a>')
        lines += ['</p>', '']

    lines += ['### 🔀 Mes dernières pull requests', '', '<table>']
    states = {'MERGED': '🟣&nbsp;mergée', 'OPEN': '🟢&nbsp;ouverte', 'CLOSED': '⚪&nbsp;fermée'}
    recent = sorted(contributions, key=lambda pr: pr['createdAt'], reverse=True)[:RECENT_PRS]
    for pr in recent:
        repository = pr['repository']
        state = 'MERGED' if pr['merged'] else pr['state']
        lines += [
            '  <tr>',
            f'    <td><img src="{avatar(repository["owner"], 32)}" width="32" height="32" alt="{repository["owner"]["login"]}"></td>',
            f'    <td><a href="{pr["url"]}">{html.escape(pr["title"])}</a><br>'
            f'<sub><a href="{repository["url"]}">{repository["nameWithOwner"]}</a> · {ago(pr["createdAt"])}</sub></td>',
            f'    <td>{states[state]}</td>',
            '  </tr>',
        ]
    lines += ['</table>', '']

    releases = {}
    merged_by_repository = defaultdict(int)
    for pr in merged:
        repository = pr['repository']
        merged_by_repository[repository['nameWithOwner']] += 1
        if repository['latestRelease']:
            releases[repository['nameWithOwner']] = repository
    latest = sorted(releases.values(), key=lambda repo: repo['latestRelease']['publishedAt'], reverse=True)
    lines += ['### 🔭 Dernières releases auxquelles j\'ai contribué', '', '<div align="center">', '<table>', '  <tr>']
    for repository in repositories:
        prs = [pr for pr in merged if pr['repository']['nameWithOwner'] == repository['nameWithOwner']]
        shipped = defaultdict(list)
        pending = []
        for pr in prs:
            release = shipped_in(pr, repository['releases']['nodes'])
            if release:
                shipped[release['tagName']].append(pr)
            else:
                pending.append(pr)
        by_tag = {release['tagName']: release for release in repository['releases']['nodes']}
        owner = repository['owner']
        lines += [
            '    <td align="center" width="50%" valign="top">',
            f'      <a href="{repository["url"]}"><img src="{avatar(owner, 96)}" width="96" height="96" alt="{owner["login"]}"></a><br>',
            f'      <h3>{html.escape(owner.get("name") or owner["login"])}</h3>',
        ]
        for tag in sorted(shipped, key=lambda tag: by_tag[tag]['publishedAt'], reverse=True)[:HIGHLIGHTED_RELEASES]:
            release = by_tag[tag]
            prs_of_tag = sorted(shipped[tag], key=lambda pr: pr['number'])
            if len(prs_of_tag) > 3:
                search = f'is:pr is:merged author:{LOGIN} base:{prs_of_tag[0]["baseRefName"]} ' \
                    f'merged:{min(pr["mergedAt"] for pr in prs_of_tag)[:10]}..{max(pr["mergedAt"] for pr in prs_of_tag)[:10]}'.replace(' ', '+').replace(':', '%3A')
                links = f'<a href="{repository["url"]}/pulls?q={search}">{len(prs_of_tag)} PR</a>'
            else:
                links = ' '.join(f'<a href="{pr["url"]}">#{pr["number"]}</a>' for pr in prs_of_tag)
            lines.append(f'      🏷️ <a href="{release["url"]}"><code>{html.escape(tag)}</code></a> <sub>{ago(release["publishedAt"])} · {links}</sub><br>')
        if pending:
            lines.append(f'      ⏳ <sub>{len(pending)} PR mergée{"s" if len(pending) > 1 else ""} dans la prochaine release</sub><br>')
        lines.append('    </td>')
    lines += ['  </tr>', '</table>', '</div>', '', '<table>']
    latest = latest[:RECENT_RELEASES]
    for row in range(0, len(latest), 4):
        lines.append('  <tr>')
        for repository in latest[row:row + 4]:
            release = repository['latestRelease']
            count = merged_by_repository[repository['nameWithOwner']]
            lines += [
                '    <td align="center" width="25%">',
                f'      <a href="{repository["url"]}"><img src="{avatar(repository["owner"], 48)}" width="48" height="48" alt="{repository["owner"]["login"]}"></a><br>',
                f'      <b><a href="{repository["url"]}">{repository["nameWithOwner"]}</a></b><br>',
                f'      🏷️ <a href="{release["url"]}"><code>{html.escape(release["tagName"])}</code></a><br>',
                f'      <sub>{ago(release["publishedAt"])} · {count} PR mergée{"s" if count > 1 else ""}</sub>',
                '    </td>',
            ]
        lines.append('  </tr>')
    lines.append('</table>')

    return '\n'.join(lines) + '\n'


def main():
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        sys.exit('GITHUB_TOKEN is required')
    target = sys.argv[1] if len(sys.argv) > 1 else 'README.md'
    with open(target, 'w') as file:
        file.write(render(fetch_pull_requests(token), fetch_repositories(token)))


if __name__ == '__main__':
    main()
