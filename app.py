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
                return await response.json()
        except aiohttp.ClientError as e:
            st.error(f"상태 확인 중 오류 발생: {e}")
            return None

def display_music_info(music_info):
    """음악 정보를 표시합니다."""
    st.subheader(f"음악 ID: {music_info.get('id', 'Unknown')}")
    st.write(f"상태: {music_info.get('status', 'Unknown')}")
    st.write(f"모델: {music_info.get('model_name', 'Unknown Model')}")
    st.write(f"생성 시간: {music_info.get('created_at', 'Unknown')}")
    
    if music_info.get('title'):
        st.write(f"제목: {music_info['title']}")
    
    if music_info.get('audio_url'):
        st.audio(music_info['audio_url'])
    
    if music_info.get('lyric'):
        st.write("가사:")
        st.text(music_info['lyric'])
    
    st.write(f"프롬프트: {music_info.get('gpt_description_prompt', 'No prompt available')}")

def extract_music_ids(result):
    """API 응답에서 음악 ID를 추출합니다."""
    return [item['id'] for item in result if 'id' in item]

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

async def send_email_async(recipient_email, audio_url, style):
    msg = MIMEMultipart()
    msg['Subject'] = f'2024 Youth E-Sports Festival에서 제작한 게임 음악이 도착했습니다.'
    msg['From'] = EMAIL_SETTINGS["SENDER_EMAIL"]
    msg['To'] = recipient_email
    
    text = MIMEText(f"2024 Youth E-Sports Festival에서 제작한 게임 음악이 도착했습니다.\n스타일: {style}\n음악 다운로드 링크: {audio_url}")
    msg.attach(text)

    try:
        server = smtplib.SMTP(EMAIL_SETTINGS["SMTP_SERVER"], EMAIL_SETTINGS["SMTP_PORT"])
        await asyncio.to_thread(server.starttls)
        await asyncio.to_thread(server.login, EMAIL_SETTINGS["SENDER_EMAIL"], EMAIL_SETTINGS["SENDER_PASSWORD"])
        await asyncio.to_thread(server.send_message, msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"이메일 전송 중 오류가 발생했습니다: {str(e)}")
        return False

async def main_async():
    st.image(HEADER_URL, use_column_width=True)
    st.title("AI 게임 음악 생성기")

    if not check_server_status():
        st.error("현재 서버에 접속할 수 없습니다. 잠시 후 다시 시도해주세요.")
        return

    idea = st.text_area("게임 음악 아이디어를 입력하세요:", 
                        placeholder="우주 탐험 게임의 시작 화면 배경음악",
                        height=100)

    style = st.radio("음악 스타일을 선택하세요:", list(MUSIC_STYLES.keys()), horizontal=True)
    
    recipient_email = st.text_input("결과를 받을 이메일 주소를 입력하세요:")

    if st.button("음악 생성"):
        with st.spinner("프롬프트 생성 중..."):
            prompt = await generate_prompt(idea, style)
            if not prompt:
                st.error("프롬프트 생성에 실패했습니다. 다시 시도해주세요.")
                return
            st.success("프롬프트가 생성되었습니다.")
            st.write("생성된 프롬프트:", prompt)

        with st.spinner("음악 생성 요청을 보내는 중..."):
            result = await generate_music_async(prompt)

        if result:
            music_ids = extract_music_ids(result)
            if not music_ids:
                st.error("음악 ID를 추출할 수 없습니다. API 응답 형식이 변경되었을 수 있습니다.")
                st.json(result)
                return

            st.success(f"음악 생성 요청이 성공적으로 전송되었습니다! 생성된 음악 수: {len(music_ids)}")

            progress_bar = st.progress(0)
            status_text = st.empty()
            music_info_placeholders = [st.empty() for _ in music_ids]

            start_time = time.time()
            while time.time() - start_time < MAX_WAIT_TIME:
                music_info = await check_music_status(music_ids)

                if music_info:
                    all_complete = True
                    for idx, info in enumerate(music_info):
                        status = info.get('status', 'unknown')
                        if status != 'complete':
                            all_complete = False
                        
                        with music_info_placeholders[idx].container():
                            display_music_info(info)

                    elapsed_time = time.time() - start_time
                    progress = min(elapsed_time / MAX_WAIT_TIME, 1.0)
                    progress_bar.progress(progress)
                    status_text.text(f"음악 생성 중... ({int(elapsed_time)}초 경과)")

                    if all_complete:
                        st.success("모든 음악 생성이 완료되었습니다!")
                        
                        if recipient_email:
                            for info in music_info:
                                if await send_email_async(recipient_email, info['audio_url'], style):
                                    st.success(f"생성된 음악 링크가 {recipient_email}로 전송되었습니다.")
                                else:
                                    st.error("이메일 전송에 실패했습니다.")
                        break

                await asyncio.sleep(10)  # 10초마다 상태 확인
            else:
                st.warning("최대 대기 시간을 초과했습니다. 일부 음악이 아직 완성되지 않았을 수 있습니다.")
        else:
            st.error("음악 생성 요청에 실패했습니다. 잠시 후 다시 시도해주세요.")

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
