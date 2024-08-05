import streamlit as st
import requests
import time
import asyncio
import aiohttp
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.audio import MIMEAudio
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from openai import OpenAI

st.set_page_config(layout="wide", page_title="AI 게임 음악 작곡")

SUNO_API_ENDPOINT = "https://suno-apiupdate-deck6s-projects.vercel.app"
MAX_WAIT_TIME = 600  # 최대 대기 시간을 10분(600초)으로 설정
HEADER_URL = "https://github.com/DECK6/gamechar/blob/main/header.png?raw=true"

# 이메일 설정
EMAIL_SETTINGS = {
    "SMTP_SERVER": "smtp.gmail.com",
    "SMTP_PORT": 587,
    "SENDER_EMAIL": "dnmdaia@gmail.com",
    "SENDER_PASSWORD": "iudy dgqr fuin lukc"
}

# 음악 스타일 정의
MUSIC_STYLES = {
    "90년대 오락실": "레트로한 8비트 게임에 칩튠 스타일을 더한 신나는 전자음악",
    "신나는 EDM": "빠른 비트의 EDM 게임음악 스타일",
    "웅장한 전투": "헤비메탈 기반의 게임 속 웅장한 전투 장면에 어울리는 스타일",
    "모험의 시작": "모험을 시작하는 기대감을 품게하는 잔잔하면서 희망찬 클래식 악기 위주의 음악"
}

# OpenAI 클라이언트 초기화 (API 키는 Streamlit의 시크릿에서 가져옴)
client = OpenAI(api_key=st.secrets["openai_api_key"])

def requests_retry_session(
    retries=5,
    backoff_factor=0.5,
    status_forcelist=(500, 502, 503, 504),
    session=None,
):
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def check_server_status():
    """서버 상태를 확인합니다."""
    try:
        response = requests_retry_session().get(f"{SUNO_API_ENDPOINT}/api/get_limit", timeout=10)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException:
        return False

async def generate_music_async(prompt):
    """인공지능이 작곡을 시작합니다."""
    payload = {
        "prompt": prompt,
        "make_instrumental": True,  # 항상 연주 버전 생성
        "wait_audio": False  # 비동기 모드 사용
    }
    headers = {
        "Content-Type": "application/json"
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(f"{SUNO_API_ENDPOINT}/api/generate", json=payload, headers=headers, timeout=30) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            st.error(f"API 호출 중 오류 발생: {e}")
            return None

async def check_music_status(music_ids):
#    """생성된 음악의 상태를 확인합니다."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{SUNO_API_ENDPOINT}/api/get?ids={','.join(music_ids)}", timeout=30) as response:
                response.raise_for_status()
                result = await response.json()
                return result if isinstance(result, list) else []
        except aiohttp.ClientError as e:
            st.error(f"상태 확인 중 오류 발생: {e}")
            return []

async def generate_prompt(idea, style):
    """GPT가 악상을 떠올리는 중입니다."""
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an assistant specialized in creating prompts for instrumental game music generation. Convert user ideas into detailed prompts suitable for AI music generation, focusing on game music characteristics without lyrics."},
                {"role": "user", "content": f"Create up to three sentences of simple prompt without description for instrumental game music based on this idea: {idea}. The music style should be: {MUSIC_STYLES[style]}"}
            ]
        )
        return completion.choices[0].message.content
    except Exception as e:
        st.error(f"프롬프트 생성 중 오류 발생: {e}")
        return None

translation_cache = {}

async def translate_to_korean(text):
#    """텍스트를 한국어로 번역합니다."""
    if text in translation_cache:
        return translation_cache[text]

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a translator specialized in translating English text to Korean. Provide a natural, context-appropriate translation."},
                {"role": "user", "content": f"Translate the following text to natural, context-appropriate Korean: {text}"}
            ]
        )
        translated_text = completion.choices[0].message.content
        translation_cache[text] = translated_text
        return translated_text
    except Exception as e:
        st.error(f"번역 중 오류 발생: {e}")
        return text

async def send_email_async(recipient_email, music_info_list):
    """작곡된 음악을 이메일로 전송합니다."""
    msg = MIMEMultipart()
    msg['Subject'] = '2024 Youth E-Sports Festival에서 작곡한 게임 음악이 도착했습니다.'
    msg['From'] = EMAIL_SETTINGS["SENDER_EMAIL"]
    msg['To'] = recipient_email

    # HTML 본문 생성
    html_content = "<html><body>"
    for idx, info in enumerate(music_info_list, 1):
        html_content += f"<h2>음악 {idx}: {info.get('title', 'Untitled')}</h2>"
        html_content += f"<p><strong>아이디어:</strong> {st.session_state.get('original_idea', 'N/A')}</p>"
        html_content += f"<p><strong>프롬프트:</strong> {info.get('gpt_description_prompt', 'No prompt available')}</p>"
        html_content += f"<p><a href='{info.get('audio_url', '#')}'>음악 다운로드 링크</a></p>"
        if info.get('image_url'):
            html_content += f"<img src='{info['image_url']}' alt='Cover Art' style='max-width:300px;'><br>"
        html_content += "<hr>"
    html_content += "</body></html>"

    msg.attach(MIMEText(html_content, 'html'))

    try:
        server = smtplib.SMTP(EMAIL_SETTINGS["SMTP_SERVER"], EMAIL_SETTINGS["SMTP_PORT"])
        server.starttls()
        server.login(EMAIL_SETTINGS["SENDER_EMAIL"], EMAIL_SETTINGS["SENDER_PASSWORD"])
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"이메일 전송 중 오류 발생: {str(e)}")
        return False

async def fetch_music_info(music_id):
#    """비동기적으로 음악 정보를 가져옵니다."""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{SUNO_API_ENDPOINT}/api/get?ids={music_id}") as response:
            if response.status == 200:
                data = await response.json()
                return data[0] if data else None
    return None

def extract_music_ids(result):
    """API 응답에서 음악 ID를 추출합니다."""
    return [item['id'] for item in result if 'id' in item]

def display_music_info(music_info):
    """음악 정보를 표시합니다."""
    st.markdown(f"### {music_info.get('title', 'Untitled')}")
    
    # 상태를 한국어로 변환
    status_mapping = {
        'submitted': '🎵 작곡 요청',
        'queued': '⌛ 대기중',
        'streaming': '🎶 작곡중(스트리밍)',
        'complete': '✅ 작곡 완료'
    }
    status = music_info.get('status', 'Unknown')
    status_korean = status_mapping.get(status, '알 수 없음')
    
    st.write(f"상태: {status_korean}")
    
    if music_info.get('audio_url'):
        st.audio(music_info['audio_url'])
    
    col1, col2 = st.columns(2)
    
    with col1:
        if music_info.get('image_url'):
            st.image(music_info['image_url'], caption="Cover Art")
    
    with col2:
        if 'original_idea' in music_info:
            st.write(f"입력한 아이디어: {music_info['original_idea']}")
        st.write(f"프롬프트: {music_info.get('gpt_description_prompt', 'No prompt available')}")

async def main_async():
    st.image(HEADER_URL, use_column_width=True)
    st.title("AI 게임 음악 작곡")

    if not check_server_status():
        st.error("현재 서버에 접속할 수 없습니다. 잠시 후 다시 시도해주세요.")
        return

    col1, col2 = st.columns([1, 1])

    with col1:
        idea = st.text_area("게임 음악 아이디어를 입력하세요:", 
                            placeholder="우주 탐험 게임의 시작 화면 배경음악",
                            height=100)
        style = st.radio("음악 스타일을 선택하세요:", list(MUSIC_STYLES.keys()), horizontal=True)
        recipient_email = st.text_input("결과를 받을 이메일 주소를 입력하세요:")

        if st.button("음악 생성"):
            with st.spinner("음악 생성 중..."):
                prompt = await generate_prompt(idea, style)
                if not prompt:
                    st.error("프롬프트 생성에 실패했습니다.")
                    return
                
                result = await generate_music_async(prompt)
                if not result:
                    st.error("음악 생성에 실패했습니다.")
                    return

                music_ids = extract_music_ids(result)
                if not music_ids:
                    st.error("음악 ID를 추출할 수 없습니다.")
                    st.json(result)  # 디버깅을 위해 전체 응답 표시
                    return

                st.session_state['music_ids'] = music_ids
                st.session_state['original_idea'] = idea
                st.session_state['generated_prompt'] = prompt
                st.session_state['translated_titles'] = {}
                st.session_state['translated_prompts'] = {}
                st.success(f"음악 생성 요청 완료! {len(music_ids)}개의 트랙이 생성 중입니다.")

    with col2:
        st.markdown("⏳ **음악 작곡에는 최대 2~3분정도 소요됩니다. 새로고침 하지 말고 기다려주세요.**")
        if 'music_ids' in st.session_state:
            status_text = st.empty()
            music_info_placeholders = [st.empty() for _ in st.session_state['music_ids']]

            start_time = time.time()
            while time.time() - start_time < MAX_WAIT_TIME:
                music_info = await check_music_status(st.session_state['music_ids'])

                if music_info:
                    all_complete = True
                    for idx, info in enumerate(music_info):
                        status = info.get('status', 'unknown')
                        if status != 'complete':
                            all_complete = False

                        # 원본 아이디어 및 번역된 프롬프트와 제목 추가
                        info['original_idea'] = st.session_state['original_idea']
                        info['gpt_description_prompt'] = st.session_state['generated_prompt']
                        
                        # 번역된 제목 및 프롬프트 추가 (한번만 번역)
                        if info['title'] not in st.session_state['translated_titles']:
                            translated_title = await translate_to_korean(info['title'])
                            st.session_state['translated_titles'][info['title']] = translated_title
                        else:
                            translated_title = st.session_state['translated_titles'][info['title']]

                        if info['gpt_description_prompt'] not in st.session_state['translated_prompts']:
                            translated_prompt = await translate_to_korean(info['gpt_description_prompt'])
                            st.session_state['translated_prompts'][info['gpt_description_prompt']] = translated_prompt
                        else:
                            translated_prompt = st.session_state['translated_prompts'][info['gpt_description_prompt']]

                        info['title'] = translated_title
                        info['gpt_description_prompt'] = translated_prompt

                        with music_info_placeholders[idx].container():
                            display_music_info(info)

#                    elapsed_time = time.time() - start_time
#                    status_text.text(f"음악 생성 중... ({int(elapsed_time)}초 경과)")

                    if all_complete:
                        st.success("모든 음악 작곡이 완료되었습니다!")
                        # 이메일 전송
                        music_info_list = [await fetch_music_info(music_id) for music_id in st.session_state['music_ids']]
                        for info in music_info_list:
                            info['original_idea'] = st.session_state['original_idea']
                        if await send_email_async(recipient_email, music_info_list):
                            st.success(f"완성된 게임 음악이 {recipient_email}로 전송되었습니다.")
                        else:
                            st.error("이메일 전송에 실패했습니다.")
                        break

                await asyncio.sleep(5)  # 5초마다 상태 확인
            else:
                st.warning("최대 대기 시간을 초과했습니다. 일부 음악이 아직 완성되지 않았을 수 있습니다.")

if __name__ == "__main__":
    asyncio.run(main_async())
