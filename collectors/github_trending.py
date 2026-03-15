"""GitHub Trending collector for AI/ML/trading repositories."""

import logging
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urljoin

import requests

from collectors.base import BaseCollector

logger = logging.getLogger(__name__)


class GitHubTrendingCollector(BaseCollector):
    """Collect trending repositories from GitHub focusing on AI/ML/trading."""

    source = "github_trending"

    # Keywords to filter relevant repositories
    RELEVANT_KEYWORDS = [
        # AI/ML keywords
        "artificial intelligence", "machine learning", "deep learning", 
        "neural network", "llm", "large language model", "gpt", "transformer",
        "diffusion", "stable diffusion", "ai", "ml", "pytorch", "tensorflow",
        "huggingface", "langchain", "openai", "anthropic", "ai-agent", "agent",
        "rag", "retrieval augmented generation", "embedding", "vector database",
        
        # Trading/Finance keywords
        "trading", "quantitative", "quant", "algorithmic trading", "backtest",
        "portfolio", "finance", "financial", "crypto", "cryptocurrency", 
        "bitcoin", "blockchain", "defi", "strategy", "market analysis",
        "risk management", "options", "futures", "derivatives", "forex",
    ]

    # Languages to focus on
    TARGET_LANGUAGES = ["Python", "JavaScript", "TypeScript", "Jupyter Notebook", "Go", "Rust"]

    def __init__(self) -> None:
        super().__init__()
        self.session = requests.Session()
        # GitHub API doesn't require auth but has rate limits (60 req/hour unauth)
        self.session.headers.update({
            'User-Agent': 'park-intel-collector/1.0',
            'Accept': 'application/vnd.github.v3+json'
        })

    def _is_relevant_repo(self, repo: dict) -> bool:
        """Check if repository is relevant to our focus areas."""
        text = f"{repo.get('name', '')} {repo.get('description', '')}".lower()
        
        # Check if any relevant keyword appears in name or description
        return any(keyword.lower() in text for keyword in self.RELEVANT_KEYWORDS)

    def _get_readme_content(self, repo: dict) -> str:
        """Fetch README content for a repository."""
        try:
            readme_url = f"https://api.github.com/repos/{repo['full_name']}/readme"
            response = self.session.get(readme_url, timeout=10)
            
            if response.status_code == 200:
                readme_data = response.json()
                # GitHub API returns base64 encoded content
                import base64
                content = base64.b64decode(readme_data['content']).decode('utf-8')
                # Take first 1000 chars as summary
                return content[:1000] + ("..." if len(content) > 1000 else "")
            else:
                logger.debug("No README found for %s", repo['full_name'])
                return ""
        except Exception as e:
            logger.debug("Failed to fetch README for %s: %s", repo['full_name'], e)
            return ""

    def _search_recent_repos(self, days_back: int = 1) -> list[dict]:
        """Search for recently created repositories using GitHub Search API."""
        # Calculate date for search query
        since_date = (datetime.utcnow() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        
        all_repos = []
        
        # Search with different strategies to get diverse results
        search_queries = [
            f"created:>{since_date} stars:>10 sort:stars",  # High stars
            f"created:>{since_date} language:Python sort:stars",  # Python repos
            f"created:>{since_date} AI OR ML OR LLM sort:stars",  # AI keywords  
            f"created:>{since_date} trading OR quant sort:stars",  # Trading keywords
        ]
        
        for query in search_queries:
            try:
                logger.info("Searching GitHub with query: %s", query)
                
                # GitHub Search API endpoint
                url = "https://api.github.com/search/repositories"
                params = {
                    'q': query,
                    'per_page': 30,  # Limit to avoid too much data
                    'sort': 'stars',
                    'order': 'desc'
                }
                
                response = self.session.get(url, params=params, timeout=15)
                response.raise_for_status()
                
                search_result = response.json()
                repos = search_result.get('items', [])
                
                logger.info("Found %d repositories for query: %s", len(repos), query)
                
                # Filter for relevant repos only
                relevant_repos = [repo for repo in repos if self._is_relevant_repo(repo)]
                all_repos.extend(relevant_repos)
                
                logger.info("Added %d relevant repositories", len(relevant_repos))
                
            except requests.exceptions.RequestException as e:
                logger.error("Failed to search GitHub with query '%s': %s", query, e)
                continue
            except Exception as e:
                logger.error("Unexpected error searching GitHub: %s", e)
                continue
        
        # Deduplicate by full_name
        seen = set()
        unique_repos = []
        for repo in all_repos:
            if repo['full_name'] not in seen:
                seen.add(repo['full_name'])
                unique_repos.append(repo)
        
        logger.info("Found %d unique relevant repositories", len(unique_repos))
        return unique_repos

    def collect(self) -> list[dict[str, Any]]:
        """Collect trending repositories from GitHub."""
        try:
            # Search for repositories from the past 24 hours
            repos = self._search_recent_repos(days_back=1)
            
            if not repos:
                logger.info("No trending repositories found")
                return []
            
            articles = []
            
            for repo in repos:
                try:
                    # Get README content for better article content
                    readme_content = self._get_readme_content(repo)
                    
                    # Prepare article content
                    description = repo.get('description', '') or "No description available"
                    content = f"{description}\n\n"
                    
                    if readme_content:
                        content += f"README Summary:\n{readme_content}"
                    
                    # Add repository stats
                    content += f"\n\nRepository Stats:\n"
                    content += f"⭐ Stars: {repo.get('stargazers_count', 0)}\n"
                    content += f"🍴 Forks: {repo.get('forks_count', 0)}\n"
                    content += f"📝 Language: {repo.get('language', 'Unknown')}\n"
                    content += f"📅 Created: {repo.get('created_at', 'Unknown')}\n"
                    
                    if repo.get('topics'):
                        content += f"🏷️ Topics: {', '.join(repo['topics'])}\n"
                    
                    # Determine tags based on repo properties
                    tags = ["github", "trending", "repository"]
                    
                    # Add language tag
                    if repo.get('language'):
                        tags.append(f"lang-{repo['language'].lower().replace(' ', '-')}")
                    
                    # Add topic tags
                    if repo.get('topics'):
                        tags.extend([f"topic-{topic}" for topic in repo['topics'][:5]])  # Limit topics
                    
                    # Add category tags based on keywords
                    repo_text = f"{repo.get('name', '')} {description}".lower()
                    if any(kw in repo_text for kw in ["ai", "ml", "gpt", "llm", "neural", "transformer"]):
                        tags.append("ai-ml")
                    if any(kw in repo_text for kw in ["trading", "quant", "finance", "crypto", "bitcoin"]):
                        tags.append("trading-finance")
                    
                    # Create unique source_id based on repo full name
                    source_id = f"github_{repo['full_name'].replace('/', '_')}"
                    
                    # Parse created date
                    published_at = None
                    if repo.get('created_at'):
                        try:
                            published_at = datetime.fromisoformat(
                                repo['created_at'].replace('Z', '+00:00')
                            ).replace(tzinfo=None)
                        except ValueError:
                            logger.debug("Failed to parse date: %s", repo.get('created_at'))
                    
                    article = {
                        "source": self.source,
                        "source_id": source_id,
                        "author": repo.get('owner', {}).get('login', ''),
                        "title": f"{repo.get('name', 'Untitled')} - {description[:100]}{'...' if len(description) > 100 else ''}",
                        "content": content,
                        "url": repo.get('html_url', ''),
                        "tags": tags,
                        "score": repo.get('stargazers_count', 0),  # Use star count as score
                        "published_at": published_at,
                    }
                    
                    articles.append(article)
                    
                except Exception as e:
                    logger.error("Error processing repo %s: %s", repo.get('full_name', 'unknown'), e)
                    continue
            
            logger.info("Successfully processed %d GitHub trending repositories", len(articles))
            return articles
            
        except Exception as e:
            logger.error("Failed to collect GitHub trending repositories: %s", e)
            return []