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

st.set_page_config(layout="wide", page_title="AI 게임 음악 생성기")

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
    "90년대 오락실": "레트로한 8비트 게임에 칩튠 스타일을 더한 전자음악",
    "신나는 EDM": "퓨처 베이스의 EDM 게임음악 스타일",
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
    """API를 사용하여 비동기적으로 음악을 생성합니다."""
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
    """생성된 음악의 상태를 확인합니다."""
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
    """GPT-4를 사용하여 게임 음악 프롬프트를 생성합니다."""
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


def extract_music_ids(result):
    """API 응답에서 음악 ID를 추출합니다."""
    music_ids = []
    if isinstance(result, list):
        for item in result:
            if isinstance(item, dict) and 'id' in item:
                music_ids.append(item['id'])
    return music_ids

def display_music_info(music_info, col1, col2):
    """음악 정보를 표시합니다."""
    with col1:
        st.markdown(f"### {music_info.get('title', 'Untitled')}")
        if music_info.get('audio_url'):
            st.audio(music_info['audio_url'])
        if music_info.get('image_url'):
            st.image(music_info['image_url'], caption="Cover Art")
    
    with col2:
        st.write("**입력한 아이디어:**")
        st.write(music_info.get('original_idea', 'No idea available'))
        st.write("**생성된 프롬프트:**")
        st.write(music_info.get('gpt_description_prompt', 'No prompt available'))


async def fetch_music_info(session, music_id):
    """비동기적으로 음악 정보를 가져옵니다."""
    async with session.get(f"{SUNO_API_ENDPOINT}/api/get?ids={music_id}") as response:
        if response.status == 200:
            data = await response.json()
            return data[0] if data else None
    return None

async def send_email_async(recipient_email, music_info_list):
    """생성된 모든 음악 정보를 포함하여 이메일을 전송합니다."""
    msg = MIMEMultipart()
    msg['Subject'] = '2024 Youth E-Sports Festival에서 제작한 게임 음악이 도착했습니다.'
    msg['From'] = EMAIL_SETTINGS["SENDER_EMAIL"]
    msg['To'] = recipient_email

    # HTML 본문 생성
    html_content = "<html><body>"
    for idx, info in enumerate(music_info_list, 1):
        html_content += f"<h2>음악 {idx}: {info['title']}</h2>"
        html_content += f"<p><strong>아이디어:</strong> {info['original_idea']}</p>"
        html_content += f"<p><strong>프롬프트:</strong> {info['gpt_description_prompt']}</p>"
        html_content += f"<p><a href='{info['audio_url']}'>음악 다운로드 링크</a></p>"
        if info['image_url']:
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

async def main_async():
    st.image(HEADER_URL, use_column_width=True)
    st.title("AI 게임 음악 생성기")

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
                    return

                st.session_state['music_ids'] = music_ids
                st.session_state['original_idea'] = idea
                st.session_state['generated_prompt'] = prompt
                st.success(f"음악 생성 요청 완료! {len(music_ids)}개의 트랙이 생성 중입니다.")

    with col2:
        if 'music_ids' in st.session_state:
            music_info_list = []
            async with aiohttp.ClientSession() as session:
                for music_id in st.session_state['music_ids']:
                    info = await fetch_music_info(session, music_id)
                    if info:
                        info['original_idea'] = st.session_state['original_idea']
                        info['gpt_description_prompt'] = st.session_state['generated_prompt']
                        music_info_list.append(info)

                        st.markdown(f"### {info.get('title', 'Untitled')}")
                        if info.get('audio_url'):
                            st.audio(info['audio_url'])
                        if info.get('image_url'):
                            st.image(info['image_url'], caption="Cover Art")
                        
                        st.write("**입력한 아이디어:**", info['original_idea'])
                        st.write("**생성된 프롬프트:**", info['gpt_description_prompt'])
                        st.markdown("---")

                # 모든 음악의 상태를 확인
                all_complete = False
                while not all_complete:
                    all_complete = True
                    for info in music_info_list:
                        updated_info = await fetch_music_info(session, info['id'])
                        if updated_info['status'] != 'complete':
                            all_complete = False
                            break
                    if not all_complete:
                        await asyncio.sleep(5)  # 5초 대기 후 다시 확인

            # 모든 음악 생성이 완료된 후 이메일 전송
            if all_complete and recipient_email:
                if await send_email_async(recipient_email, music_info_list):
                    st.success(f"생성된 음악 정보가 {recipient_email}로 전송되었습니다.")
                else:
                    st.error("이메일 전송에 실패했습니다.")

if __name__ == "__main__":
    asyncio.run(main_async())
