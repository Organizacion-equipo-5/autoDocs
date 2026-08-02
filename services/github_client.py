# services/github_client.py

import re
import requests

def extract_repo_info(github_url):
    """
    Extrae el owner y nombre del repositorio desde una URL de GitHub
    """
    url = github_url.strip()
    
    patterns = [
        r'github\.com[:/]([^/]+)/([^/.]+)(?:\.git)?/?$',
        r'github\.com/([^/]+)/([^/]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            owner = match.group(1)
            repo = match.group(2)
            repo = re.sub(r'\?.*$', '', repo)
            return owner, repo
    
    raise ValueError(f"No se pudo extraer información del repositorio desde: {github_url}")

def get_contributors_from_api(github_url):
    """
    Obtiene los colaboradores de un repositorio de GitHub usando la API pública
    """
    owner, repo_name = extract_repo_info(github_url)
    
    try:
        url = f"https://api.github.com/repos/{owner}/{repo_name}/contributors"
        
        response = requests.get(url, headers={
            'Accept': 'application/vnd.github.v3+json'
        })
        
        if response.status_code == 404:
            return {
                "contributors": [],
                "message": f"Repositorio no encontrado: {owner}/{repo_name}"
            }
        elif response.status_code == 403:
            return {
                "contributors": [],
                "message": "Límite de API de GitHub alcanzado. Intenta más tarde."
            }
        elif response.status_code != 200:
            raise Exception(f"Error en GitHub API: {response.status_code}")
        
        data = response.json()
        
        if isinstance(data, dict) and data.get('message'):
            return {
                "contributors": [],
                "message": data.get('message', 'Error desconocido')
            }
        
        if not data:
            return {
                "contributors": [],
                "message": "No se encontraron colaboradores para este repositorio"
            }
        
        contributors_data = []
        total_commits = 0
        
        for contributor in data:
            user_info = {
                'username': contributor.get('login', ''),
                'name': contributor.get('login', ''),
                'email': '',
                'avatar_url': contributor.get('avatar_url', ''),
                'commits': contributor.get('contributions', 0),
                'role': 'contributor'
            }
            
            contributors_data.append(user_info)
            total_commits += contributor.get('contributions', 0)
        
        contributors_data.sort(key=lambda x: x['commits'], reverse=True)
        
        active_days = _estimate_active_days(owner, repo_name)
        
        return {
            'contributors': contributors_data,
            'total_commits': total_commits,
            'unique_authors': len(contributors_data),
            'active_days': active_days,
            'repo_url': f"https://github.com/{owner}/{repo_name}",
            'repo_name': f"{owner}/{repo_name}"
        }
        
    except requests.exceptions.RequestException as e:
        raise Exception(f"Error de conexión con GitHub API: {str(e)}")
    except Exception as e:
        raise Exception(f"Error al obtener colaboradores: {str(e)}")

def _estimate_active_days(owner, repo_name):
    """
    Estima los días activos del repositorio basado en commits recientes
    """
    try:
        url = f"https://api.github.com/repos/{owner}/{repo_name}/commits"
        params = {'per_page': 100}
        
        response = requests.get(url, params=params, headers={
            'Accept': 'application/vnd.github.v3+json'
        })
        
        if response.status_code != 200:
            return 0
        
        data = response.json()
        if not data:
            return 0
        
        dates = set()
        for commit in data:
            if commit.get('commit', {}).get('author', {}).get('date'):
                date_str = commit['commit']['author']['date'][:10]
                dates.add(date_str)
        
        return len(dates)
    except:
        return 0