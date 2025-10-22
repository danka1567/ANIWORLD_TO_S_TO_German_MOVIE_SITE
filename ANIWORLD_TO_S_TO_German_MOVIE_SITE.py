import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, urlparse
import json
import time
import os

# Set page configuration
st.set_page_config(
    page_title="Aniworld Scraper",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

class AniworldScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.base_url = "https://aniworld.to"
        self.tmdb_api_key = "6fad3f86b8452ee232deb7977d7dcf58"
        self.tmdb_base_url = "https://api.themoviedb.org/3"
    
    def fetch_page(self, url):
        """Fetch the webpage content"""
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            st.error(f"Error fetching page: {e}")
            return None
    
    def get_tmdb_id(self, anime_name):
        """Get TMDB ID using TMDB API search"""
        try:
            # Search for TV show (anime)
            search_url = f"{self.tmdb_base_url}/search/tv"
            params = {
                'api_key': self.tmdb_api_key,
                'query': anime_name,
                'language': 'en-US'
            }
            
            response = requests.get(search_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data['results']:
                # Return the first result's ID
                return str(data['results'][0]['id'])
            else:
                # If no TV results, try movie search
                search_url = f"{self.tmdb_base_url}/search/movie"
                response = requests.get(search_url, params=params)
                response.raise_for_status()
                data = response.json()
                
                if data['results']:
                    return str(data['results'][0]['id'])
                
            return ""
            
        except Exception as e:
            st.error(f"Error fetching TMDB ID for {anime_name}: {e}")
            return ""
    
    def extract_anime_info(self, soup, url):
        """Extract main anime information including TMDB and IMDB IDs"""
        anime_info = {
            "main_title": "",
            "tmdb_id": "",
            "imdb_id": "",
            "serial_number": ""
        }
        
        # Extract main title
        title_element = soup.find('h1') or soup.find('title')
        if title_element:
            anime_info["main_title"] = title_element.get_text(strip=True)
        
        # Extract serial number from URL
        serial_match = re.search(r'/anime/stream/([^/]+)', url)
        if serial_match:
            anime_name = serial_match.group(1)
            anime_info["serial_number"] = anime_name
            
            # Get TMDB ID using the anime name from URL
            with st.spinner(f"Searching TMDB for: {anime_name}"):
                tmdb_id = self.get_tmdb_id(anime_name.replace('-', ' ').title())
                anime_info["tmdb_id"] = tmdb_id
                if tmdb_id:
                    st.success(f"✅ Found TMDB ID: {tmdb_id}")
                else:
                    st.warning("❌ No TMDB ID found")
        
        # Try to extract IMDB ID from page meta tags
        meta_tags = soup.find_all('meta')
        for meta in meta_tags:
            content = meta.get('content', '')
            
            # Look for IMDB ID
            if 'imdb.com/title/tt' in content:
                imdb_match = re.search(r'tt(\d+)', content)
                if imdb_match:
                    anime_info["imdb_id"] = f"tt{imdb_match.group(1)}"
                    st.success(f"✅ Found IMDB ID: {anime_info['imdb_id']}")
                    break
        
        return anime_info
    
    def extract_season_info(self, soup):
        """Extract season information"""
        season_info = {}
        
        # Extract season title and number
        season_div = soup.find('div', itemprop='name')
        if season_div:
            season_info['title'] = season_div.get_text(strip=True)
        
        meta_season = soup.find('meta', itemprop='seasonNumber')
        if meta_season:
            season_info['number'] = meta_season.get('content')
        
        return season_info
    
    def map_hoster_to_language(self, hosters, languages):
        """Map hosters to specific language types based on the pattern"""
        language_mapping = {}
        
        # Create mapping based on typical patterns
        for i, hoster in enumerate(hosters):
            if i < len(languages):
                lang = languages[i]
                if "Deutsch/German" in lang:
                    language_mapping["german_video"] = hoster
                elif "Mit deutschem Untertitel" in lang:
                    language_mapping["original_with_german_sub_Video"] = hoster
                elif "Englisch" in lang:
                    language_mapping["original_with_english_sub_Video"] = hoster
        
        # Fallback: if pattern doesn't match, assign based on position
        if not language_mapping:
            if len(hosters) >= 1:
                language_mapping["german_video"] = hosters[0]
            if len(hosters) >= 2:
                language_mapping["original_with_german_sub_Video"] = hosters[1]
            if len(hosters) >= 3:
                language_mapping["original_with_english_sub_Video"] = hosters[2]
        
        return language_mapping
    
    def extract_episode_titles(self, title_cell):
        """Extract both German and English episode titles"""
        titles = {}
        
        # Find the strong tag for German title
        german_title = title_cell.find('strong')
        if german_title:
            titles['german'] = german_title.get_text(strip=True)
        
        # Find the span tag for English title
        english_span = title_cell.find('span')
        if english_span:
            english_text = english_span.get_text(strip=True)
            # Extract just the English title part (remove episode number in brackets)
            english_match = re.search(r'(.+?)\s*\[Episode\s*\d+\]', english_text)
            if english_match:
                titles['english'] = english_match.group(1).strip()
            else:
                titles['english'] = english_text
        
        return titles
    
    def extract_episode_data(self, soup):
        """Extract all episode data from the table"""
        episodes = []
        
        # Find all episode rows
        episode_rows = soup.find_all('tr', itemprop='episode')
        
        for row in episode_rows:
            episode_data = {}
            
            # Extract episode number
            episode_number_meta = row.find('meta', itemprop='episodeNumber')
            if episode_number_meta:
                episode_data['episode_number'] = episode_number_meta.get('content')
            
            # Extract episode URL
            episode_link = row.find('a', itemprop='url')
            if episode_link:
                episode_data['url'] = urljoin(self.base_url, episode_link.get('href'))
            
            # Extract episode titles (German and English)
            title_cell = row.find('td', class_='seasonEpisodeTitle')
            if title_cell:
                titles = self.extract_episode_titles(title_cell)
                episode_data.update(titles)
            
            # Extract hosters
            hoster_cell = row.find_all('td')[2]  # Third column
            hoster_icons = hoster_cell.find_all('i', class_='icon')
            hosters = [icon.get('title') for icon in hoster_icons if icon.get('title')]
            
            # Extract languages
            language_cell = row.find_all('td')[3]  # Fourth column
            flags = language_cell.find_all('img', class_='flag')
            languages = [flag.get('title') for flag in flags if flag.get('title')]
            
            # Map hosters to language types
            language_hosters = self.map_hoster_to_language(hosters, languages)
            episode_data.update(language_hosters)
            
            episodes.append(episode_data)
        
        return episodes
    
    def extract_redirect_urls_for_episode(self, episode_url, episode_data):
        """Extract redirect URLs using your method"""
        HEADERS = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36"
        }
        
        try:
            # Get page HTML
            response = requests.get(episode_url, headers=HEADERS)
            response.raise_for_status()
            html = response.text

            # Parse HTML with BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")

            # Extract all <li> with redirect links
            hosters = soup.find_all("li", attrs={"data-link-target": True})

            # Collect links grouped by hoster name
            voe_links = ["", "", ""]       # EN, DE_DUB, DE_SUB
            filemoon_links = ["", "", ""]
            vidmoly_links = ["", "", ""]

            # Map data-lang-key to index
            lang_index = {"2": 0, "1": 1, "3": 2}  # 2=EN, 1=DE_DUB, 3=DE_SUB

            for li in hosters:
                hoster_icon = li.find("i", class_="icon")
                if not hoster_icon:
                    continue

                hoster_name = hoster_icon.get("title", "").strip()
                link = li.get("data-link-target")
                lang_key = li.get("data-lang-key", "")

                if link and lang_key in lang_index:
                    full_link = urljoin(self.base_url, link)
                    idx = lang_index[lang_key]

                    if "VOE" in hoster_name:
                        voe_links[idx] = full_link
                    elif "Filemoon" in hoster_name:
                        filemoon_links[idx] = full_link
                    elif "Vidmoly" in hoster_name:
                        vidmoly_links[idx] = full_link

            return {
                "german_video_URL_VOE_En_Link": voe_links[0],
                "german_video_URL_VOE_De_Dub_Link": voe_links[1],
                "german_video_URL_VOE_Original_lang_De_Sub_Link": voe_links[2],
                "german_video_URL_VIDMOLY_En_Link": vidmoly_links[0],
                "german_video_URL_VIDMOLY_De_Dub_Link": vidmoly_links[1],
                "german_video_URL_VIDMOLY_Original_lang_De_Sub_Link": vidmoly_links[2],
                "german_video_URL_FILEMOON_En_Link": filemoon_links[0],
                "german_video_URL_FILEMOON_De_Dub_Link": filemoon_links[1],
                "german_video_URL_FILEMOON_Original_lang_De_Sub_Link": filemoon_links[2],
            }
            
        except Exception as e:
            st.error(f"Error extracting redirect URLs: {e}")
            return {}
    
    def process_season(self, url):
        """Process a single season and return results"""
        results = {}
        
        # Step 1: Scrape episode data
        with st.spinner(f"Scraping data from: {url}"):
            html_content = self.fetch_page(url)
            if not html_content:
                return None
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract season information
            season_info = self.extract_season_info(soup)
            
            # Extract episode data
            episodes = self.extract_episode_data(soup)
            
            if not episodes:
                st.error("No episodes found!")
                return None
        
        # Extract anime info with TMDB API
        anime_info = self.extract_anime_info(soup, url)
        season_number = season_info.get('number', 1)
        
        # Display season information
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Season", season_number)
        with col2:
            st.metric("Total Episodes", len(episodes))
        with col3:
            st.metric("TMDB ID", anime_info["tmdb_id"] or "Not Found")
        with col4:
            st.metric("IMDB ID", anime_info["imdb_id"] or "Not Found")
        
        # Step 2: Display episodes table
        st.subheader("📺 Episode List")
        episode_data = []
        for episode in episodes:
            episode_data.append({
                "Episode": episode['episode_number'],
                "German Title": episode.get('german', ''),
                "English Title": episode.get('english', ''),
                "German Video": episode.get('german_video', ''),
                "German Sub": episode.get('original_with_german_sub_Video', ''),
                "English Sub": episode.get('original_with_english_sub_Video', '')
            })
        
        st.dataframe(episode_data, use_container_width=True)
        
        # Step 3: Process redirect URLs
        if st.button("🚀 Extract Redirect URLs", key=f"redirect_{season_number}"):
            with st.spinner("Extracting redirect URLs for all episodes..."):
                redirect_results = []
                progress_bar = st.progress(0)
                
                for i, episode in enumerate(episodes):
                    episode_url = episode['url']
                    episode_num = episode['episode_number']
                    
                    # Update progress
                    progress = (i + 1) / len(episodes)
                    progress_bar.progress(progress)
                    
                    # Extract redirect URLs
                    redirect_urls = self.extract_redirect_urls_for_episode(episode_url, episode)
                    
                    # Create custom format entry
                    episode_data = {
                        "main_title": anime_info["main_title"],
                        "tmdb_id": anime_info["tmdb_id"],
                        "imdb_id": anime_info["imdb_id"],
                        "ORIGINAL_serial number": episode_num,
                        "Sesson_number": season_number,
                        "episode_number": episode_num,
                        "original_url": episode_url,
                        "german_title": episode.get('german', ''),
                        "english_title": episode.get('english', '')
                    }
                    
                    # Add redirect URLs
                    episode_data.update(redirect_urls)
                    redirect_results.append(episode_data)
                    
                    # Add delay to be respectful to the server
                    time.sleep(1)
                
                progress_bar.empty()
                
                # Save redirect results
                redirect_filename = f"season_{season_number}_redirects_custom.json"
                with open(redirect_filename, 'w', encoding='utf-8') as f:
                    json.dump(redirect_results, f, ensure_ascii=False, indent=4)
                
                # Display download button for redirect JSON
                with open(redirect_filename, "r", encoding="utf-8") as file:
                    st.download_button(
                        label=f"📥 Download Season {season_number} Redirects JSON",
                        data=file.read(),
                        file_name=redirect_filename,
                        mime="application/json",
                        key=f"download_redirect_{season_number}"
                    )
                
                # Display sample of the data
                st.subheader("🎯 Sample Redirect Data")
                if redirect_results:
                    st.json(redirect_results[0])
                
                results['redirect_file'] = redirect_filename
                results['redirect_data'] = redirect_results
            
        results['season_info'] = season_info
        results['anime_info'] = anime_info
        results['episodes'] = episodes
        
        return results

def main():
    # Sidebar
    st.sidebar.title("🎬 Aniworld Scraper")
    st.sidebar.markdown("""
    Extract episode information and redirect URLs from Aniworld.to
    
    **Features:**
    - Extract episode lists
    - Get TMDB/IMDB IDs
    - Extract redirect URLs
    - Export to JSON format
    """)
    
    # Main content
    st.title("🎬 Aniworld Anime Scraper")
    st.markdown("---")
    
    # URL input section
    st.subheader("🔗 Enter Aniworld URLs")
    
    # Default URLs
    default_urls = [
        "https://aniworld.to/anime/stream/naruto",
        "https://aniworld.to/anime/stream/naruto/staffel-2"
    ]
    
    # URL input
    url_input = st.text_area(
        "Enter Aniworld URLs (one per line):",
        value="\n".join(default_urls),
        height=100,
        help="Enter URLs like: https://aniworld.to/anime/stream/naruto"
    )
    
    urls = [url.strip() for url in url_input.split('\n') if url.strip()]
    
    if st.button("🚀 Start Scraping", type="primary"):
        if not urls:
            st.error("Please enter at least one URL")
            return
        
        scraper = AniworldScraper()
        
        # Process each URL
        for i, url in enumerate(urls):
            st.markdown(f"---")
            st.subheader(f"🎯 Processing: {url}")
            
            try:
                results = scraper.process_season(url)
                
                if results:
                    st.success(f"✅ Successfully processed Season {results['season_info'].get('number', i+1)}")
                    
                    # Display download button for episode data
                    episode_filename = f"season_{results['season_info'].get('number', i+1)}_episodes.json"
                    episode_data = {
                        "season": int(results['season_info'].get('number', i+1)),
                        "episodes": results['episodes']
                    }
                    
                    # Create download button for episode data
                    episode_json = json.dumps(episode_data, ensure_ascii=False, indent=2)
                    st.download_button(
                        label=f"📥 Download Season {results['season_info'].get('number', i+1)} Episodes JSON",
                        data=episode_json,
                        file_name=episode_filename,
                        mime="application/json",
                        key=f"download_episodes_{i}"
                    )
                    
            except Exception as e:
                st.error(f"❌ Error processing {url}: {str(e)}")
        
        st.balloons()
        st.success("🎉 All URLs processed successfully!")

    # Instructions section
    with st.expander("📖 How to use"):
        st.markdown("""
        1. **Enter URLs**: Paste Aniworld season URLs in the text area
        2. **Click Start**: Press the 'Start Scraping' button
        3. **View Results**: See episode information and metadata
        4. **Extract Redirects**: Click the 'Extract Redirect URLs' button for each season
        5. **Download Data**: Use the download buttons to save JSON files
        
        **URL Format**: `https://aniworld.to/anime/stream/SERIES_NAME/staffel-SEASON_NUMBER`
        """)
    
    # Example section
    with st.expander("📚 Example URLs"):
        st.markdown("""
        **Popular Anime Examples:**
        - `https://aniworld.to/anime/stream/naruto`
        - `https://aniworld.to/anime/stream/one-piece`
        - `https://aniworld.to/anime/stream/attack-on-titan`
        - `https://aniworld.to/anime/stream/demon-slayer`
        - `https://aniworld.to/anime/stream/my-hero-academia`
        """)

if __name__ == "__main__":
    main()
