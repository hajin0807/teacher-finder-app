import streamlit as st
import pandas as pd
import requests
import json
import os
import time
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from googleapiclient.discovery import build
from anthropic import Anthropic
import csv
import io
import re
import concurrent.futures

# 페이지 기본 설정
st.set_page_config(
    page_title="선생님 발굴 자동화 프로그램",
    page_icon="🧑‍🏫",
    layout="wide"
)

# 세션 상태 초기화
if 'current_step' not in st.session_state:
    st.session_state['current_step'] = 0
if 'total_steps' not in st.session_state:
    st.session_state['total_steps'] = 5  # 총 5단계 프로세스
if 'progress' not in st.session_state:
    st.session_state['progress'] = 0  # 진행률 (0-100%)
if 'comments_data' not in st.session_state:
    st.session_state['comments_data'] = None
if 'keywords_analysis' not in st.session_state:
    st.session_state['keywords_analysis'] = None
if 'scripts_data' not in st.session_state:
    st.session_state['scripts_data'] = None
if 'matching_results' not in st.session_state:
    st.session_state['matching_results'] = None
if 'email_content' not in st.session_state:
    st.session_state['email_content'] = None

# API 키 설정
YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"]
CLAUDE_API_KEY = st.secrets["CLAUDE_API_KEY"]

# 디버깅용 (개발 완료 후 제거)
# API 키 정보 표시 (옵션)
st.sidebar.write("**API 키 상태**")
masked_key = f"{YOUTUBE_API_KEY[:5]}...{YOUTUBE_API_KEY[-5:]}"
st.sidebar.write(f"YouTube API 키: {masked_key}")
# Google Sheets API 설정 함수
def setup_google_sheets():
    """Google Sheets API에 연결하기 위한 설정"""
    scope = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ]
    import json
    service_account_info = json.loads(st.secrets["gcp_service_account"])
    credentials = ServiceAccountCredentials.from_dict(service_account_info, scope)
    client = gspread.authorize(credentials)
    return client

# 스프레드시트에서 이미 수집된 채널 목록을 가져오는 함수
def get_collected_channels_from_sheet(spreadsheet_url):
    """Google 스프레드시트에서 이미 수집된 채널 목록을 가져옵니다."""
    try:
        st.write(f"✅ 이미 수집된 채널 목록을 시트에서 가져오는 중...")
        client = setup_google_sheets()
        
        # 스프레드시트 열기
        spreadsheet = client.open_by_url(spreadsheet_url)
        
        # 리스트업 워크시트 찾기
        try:
            worksheet = spreadsheet.worksheet("리스트업")
        except gspread.exceptions.WorksheetNotFound:
            st.warning("⚠️ '리스트업' 시트가 없어 중복 채널 필터링을 적용할 수 없습니다.")
            return set()
        
        # 데이터 가져오기
        all_values = worksheet.get_all_values()
        
        # 채널명 열(B열) 데이터 추출 (헤더 제외)
        if len(all_values) > 1:
            # 채널명 열은 B열(인덱스 1)
            channels = set(row[1] for row in all_values[1:] if len(row) > 1 and row[1].strip())
            st.success(f"✅ {len(channels)}개의 채널을 시트에서 가져왔습니다.")
            return channels
        else:
            st.info("⚠️ 시트에 채널 정보가 없습니다.")
            return set()
            
    except Exception as e:
        st.error(f"❌ 시트에서 채널 목록을 가져오는 중 오류 발생: {str(e)}")
        return set()

# 자동화 실행 함수 추가
# 아래는 run_full_automation 함수의 전체 구조를 수정한 예시입니다.
# 실제 적용시 함수 전체를 이렇게 대체하시기 바랍니다.

def run_full_automation(keyword, max_videos, max_comments, max_videos_per_keyword, filter_duplicate_channels, min_subscribers, spreadsheet_url):
    """전체 과정을 자동으로 실행하는 함수"""
    try:
        st.write("🚀 자동화 프로세스 시작...")
        
        # 1. 데이터 수집
        st.write("1️⃣ 댓글 데이터 수집 단계 시작")
        comments = collect_comments_by_keyword(keyword, max_videos, max_comments)
        if not comments:
            st.error("❌ 댓글 수집 실패. 프로세스를 중단합니다.")
            return False
        
        st.session_state['comments_data'] = comments
        st.session_state['initial_search_keyword'] = keyword
        
        # 결과를 바로 expander로 표시
        st.success(f"✅ {len(comments)}개의 댓글 수집 완료")
        with st.expander("📋 수집된 댓글 데이터 보기", expanded=False):
            # 댓글 데이터 표 형식으로 표시
            comments_df = pd.DataFrame([
                {
                    'video_title': c.get('video_title', ''),
                    'author': c.get('author', ''),
                    'text': c.get('text', '')[:100] + '...' if len(c.get('text', '')) > 100 else c.get('text', ''),
                    'likes': c.get('likes', 0)
                }
                for c in comments
            ])
            st.dataframe(comments_df)
        
        update_progress(1, 1.0)
        
        # 2. 키워드 분석
        st.write("2️⃣ 키워드 분석 단계 시작")
        analysis_result = analyze_comments_with_claude(comments, keyword)
        if not analysis_result:
            st.error("❌ 키워드 분석 실패. 프로세스를 중단합니다.")
            return False
        
        structured_analysis = extract_structured_data_from_analysis(analysis_result)
        st.session_state['keywords_analysis'] = structured_analysis
        
        # 결과를 바로 expander로 표시
        st.success("✅ 키워드 분석 완료")
        with st.expander("📋 키워드 분석 결과 보기", expanded=False):
            st.write(structured_analysis.get('raw_text', '분석 결과가 없습니다.'))
        
        update_progress(2, 1.0)
        
        # 유튜브 검색 최적화 키워드 추출
        keywords_text = structured_analysis.get('raw_text', '')
        search_keywords = []
        
        if "유튜브 검색 최적화 키워드" in keywords_text:
            search_section = keywords_text.split("유튜브 검색 최적화 키워드")[1]
            keyword_pattern = r'\d+\.\s*(.+)'
            matches = re.findall(keyword_pattern, search_section)
            
            for k in matches:
                if k and k.strip():
                    search_keywords.append(k.strip())
            
            search_keywords = search_keywords[:10]
        
        if not search_keywords:
            default_keywords = [
                "스피치 자신감 키우는 5분 연습법",
                "논리적 스피치 두괄식 말하기 기법",
                "스피치 리듬감 3가지 비밀",
                "말더듬 극복하는 스피치 리듬 훈련",
                "청중을 사로잡는 스피치 기술"
            ]
            search_keywords = default_keywords
            st.warning("⚠️ 유튜브 검색 최적화 키워드를 찾지 못했습니다. 기본 키워드를 사용합니다.")
        
        # 3. 스크립트 수집
        st.write("3️⃣ 스크립트 수집 단계 시작")
        scripts_data = collect_scripts_by_keywords(
            search_keywords, 
            max_videos_per_keyword,
            filter_duplicate_channels,
            min_duration_seconds=180,
            max_duration_seconds=1800,
            max_age_days=1000,
            min_subscribers=min_subscribers,  # 최소 구독자 수 파라미터 추가
            spreadsheet_url=spreadsheet_url
        )
        
        if not scripts_data:
            st.error("❌ 스크립트 수집 실패. 프로세스를 중단합니다.")
            return False
            
        st.session_state['scripts_data'] = scripts_data
        
        # 결과를 바로 expander로 표시
        st.success(f"✅ {len(scripts_data)}개 스크립트 수집 완료")
        with st.expander("📋 수집된 스크립트 보기", expanded=False):
            # 채널별 그룹화 표시
            channel_groups = {}
            for script in scripts_data:
                channel = script['channel_name']
                if channel not in channel_groups:
                    channel_groups[channel] = []
                channel_groups[channel].append(script)
            
            # 채널별 통계 표시
            st.subheader("채널별 수집 현황")
            for channel, scripts in channel_groups.items():
                st.write(f"**{channel}**: {len(scripts)}개 영상")
            
            # 스크립트 간략 정보 표시
            st.subheader("수집된 스크립트 목록")
            for i, script in enumerate(scripts_data):
                st.markdown(f"**{i+1}. {script['title']} - {script['channel_name']}**")
                st.write(f"조회수: {script.get('view_count', 'N/A')}")
                st.write(f"구독자 수: {script.get('subscriber_count', 'N/A')}명")  # 구독자 수 표시
                st.write(f"링크: {script['video_link']}")
                st.write("스크립트 미리보기:")
                preview = script.get('script', '')[:500] + '...' if len(script.get('script', '')) > 500 else script.get('script', '')
                st.text(preview)
                st.markdown("---")
        
        update_progress(3, 1.0)
    
        # 4. 콘텐츠 매칭 단계
        st.write("4️⃣ 콘텐츠 매칭 단계 시작")
        matching_result = match_content_with_claude(
            st.session_state['keywords_analysis'],
            st.session_state['scripts_data']
        )
        
        if not matching_result:
            st.error("❌ 콘텐츠 매칭 실패. 프로세스를 중단합니다.")
            return False
            
        st.session_state['matching_results'] = matching_result
        
        # 추천 영상 추출
        st.session_state['recommended_videos'] = extract_recommended_videos(matching_result)
        recommended_count = len([v for v in st.session_state['recommended_videos'] if v["score"] >= 5.0])


        
        # 결과를 바로 expander로 표시
        st.success(f"✅ 콘텐츠 매칭 완료. 추천 영상(5.0점 이상): {recommended_count}개")
        with st.expander("📋 매칭 결과 및 추천 영상 보기", expanded=False):
            # 전체 매칭 결과 표시 (버튼으로 대체)
            if st.checkbox("전체 매칭 분석 결과 보기", key="show_full_matching"):
                st.write(matching_result)
            
            # 추천 선생님 목록 표시 - 8.5점 이상인 영상만 표시
            st.subheader("⭐ 추천 선생님 목록 ⭐")
            recommended_videos = [v for v in st.session_state['recommended_videos'] if v['score'] >= 5.0]
            
            if recommended_videos:
                for i, video in enumerate(recommended_videos, 1):
                    # 각 영상을 구분선으로 구분
                    if i > 1:
                        st.markdown("---")
                    
                    col1, col2 = st.columns([1, 3])
                    
                    with col1:
                        # 유튜브 섬네일 표시
                        if video.get('video_id'):
                            thumbnail_url = f"https://img.youtube.com/vi/{video['video_id']}/mqdefault.jpg"
                            st.image(thumbnail_url, caption=f"#{i}")
                    
                    with col2:
                        st.markdown(f"### **{video['title']}**")
                        st.markdown(f"**채널**: {video['channel']}")
                        st.markdown(f"**관련성 점수**: **{video['score']}/10**")
                        if video.get('url'):
                            st.markdown(f"**링크**: [{video['url']}]({video['url']})")
            else:
                st.warning("5.0점 이상인 추천 선생님이 없습니다.")
        
        update_progress(4, 1.0)
        
        # 5. 영업 이메일 생성
        st.write("5️⃣ 영업 이메일 생성 단계 (임시 중단)")
        st.warning("⚠️ 이메일 생성 기능은 일시적으로 중단되었습니다.")
        update_progress(4, 1.0)  # 이 단계 완료로 표시

        # 6. 스프레드시트에 저장 (이메일 없이)
        st.write("6️⃣ 스프레드시트 저장 단계 시작")
        try:
            # 빈 이메일 데이터 생성 (이메일 내용이 없는 객체)
            empty_emails = {}
            recommended_videos = [v for v in st.session_state['recommended_videos'] if v['score'] >= 5.0]
    
            for video in recommended_videos:
                empty_emails[video['video_id']] = {
                    'title': video['title'],
                    'channel': video['channel'],
                    'score': video['score'],
                    'email': ''  # 빈 이메일
                }
    
            st.write(f"✅ {len(empty_emails)}개의 빈 이메일 데이터로 스프레드시트 저장을 진행합니다.")
            st.write(f"✅ 사용할 스프레드시트 URL: {spreadsheet_url}")
    
            success, message = save_matching_results_to_sheet(
                spreadsheet_url,
                matching_result,
                st.session_state['recommended_videos'],
                empty_emails  # 빈 이메일 데이터 전달
            )
    
            if success:
                st.success(f"✅ {message}")
            else:
                st.error(f"❌ {message}")
        except Exception as e:
            st.error(f"❌ 스프레드시트 저장 중 오류 발생: {str(e)}")
            st.exception(e)  # 상세 오류 표시

        st.balloons()
        st.success("🎉 전체 자동화 프로세스가 완료되었습니다!")
        return True
        
    except Exception as e:
        st.error(f"❌ 자동화 프로세스 중 오류 발생: {str(e)}")
        st.exception(e)
        return False

        st.balloons()
        st.success("🎉 전체 자동화 프로세스가 완료되었습니다!")
        return True  # 이 return 문은 run_full_automation 함수의 적절한 들여쓰기 레벨에 맞춰야 함
    

        
        st.write("5️⃣ 영업 이메일 생성 단계 시작")
        recommended_videos = [v for v in st.session_state['recommended_videos'] if v['score'] >= 5.0]
        
        if not recommended_videos:
            st.warning("⚠️ 5.0점 이상인 추천 영상이 없습니다. 이메일 생성 및 저장을 건너뜁니다.")
            return True
            
        all_emails = {}
        for i, video in enumerate(recommended_videos):
            progress_text = f"({i+1}/{len(recommended_videos)}) {video['title']} 처리 중..."
            st.write(progress_text)
            
            try:
                email_content = generate_email_with_claude(
                    video,
                    st.session_state['keywords_analysis'],
                    st.session_state['scripts_data']
                )
                if email_content:
                    all_emails[video['video_id']] = {
                        'title': video['title'],
                        'channel': video['channel'],
                        'score': video['score'],
                        'email': email_content
                    }
            except Exception as e:
                st.error(f"'{video['title']}' 이메일 생성 중 오류 발생: {str(e)}")
        
        st.session_state['all_emails'] = all_emails
        
        # 결과를 바로 expander로 표시
        st.success(f"✅ {len(all_emails)}개 이메일 생성 완료")
        with st.expander("📋 생성된 이메일 보기", expanded=False):
            if all_emails:
                for video_id, data in all_emails.items():
                    st.markdown(f"**{data['channel']} - {data['title']} (점수: {data['score']}/10)**")
                    st.text(data['email'])
                    st.markdown("---")  # 구분선 추가
            else:
                st.warning("생성된 이메일이 없습니다.")
        
        # 6. 스프레드시트에 저장
        st.write("6️⃣ 스프레드시트 저장 단계 시작")
        try:
            if not all_emails:
                st.warning("⚠️ 생성된 이메일이 없어 스프레드시트에 저장할 데이터가 없습니다.")
            else:
                st.write(f"✅ {len(all_emails)}개의 이메일과 매칭 결과를 스프레드시트에 저장합니다.")
                st.write(f"✅ 사용할 스프레드시트 URL: {spreadsheet_url}")
                
                success, message = save_matching_results_to_sheet(
                    spreadsheet_url,
                    matching_result,
                    st.session_state['recommended_videos'],
                    all_emails
                )
                
                if success:
                    st.success(f"✅ {message}")
                else:
                    st.error(f"❌ {message}")
        except Exception as e:
            st.error(f"❌ 스프레드시트 저장 중 오류 발생: {str(e)}")
            st.exception(e)  # 상세 오류 표시
        
        st.balloons()
        st.success("🎉 전체 자동화 프로세스가 완료되었습니다!")
        return True
        
    except Exception as e:
        st.error(f"❌ 자동화 프로세스 중 오류 발생: {str(e)}")
        st.exception(e)
        return False
# 스프레드시트에 영업 이메일 저장 함수 (순서 변경)
def save_matching_results_to_sheet(spreadsheet_url, matching_results, recommended_videos, all_emails=None):
    """매칭된 선생님 목록과 영업 이메일을 Google 스프레드시트에 저장"""
    try:
        st.write(f"✅ Google Sheets API 연결 시작")
        client = setup_google_sheets()
        st.write(f"✅ Google Sheets API 연결 성공")
        
        # 스프레드시트 열기
        st.write(f"✅ 스프레드시트 열기 시도: {spreadsheet_url}")
        spreadsheet = client.open_by_url(spreadsheet_url)
        st.write(f"✅ 스프레드시트 열기 성공")
        
        # 이메일 워크시트 (없으면 생성)
        if all_emails:
            st.write(f"✅ 저장할 이메일 데이터: {len(all_emails)}개")
            
            try:
                email_worksheet = spreadsheet.worksheet("리스트업")
                st.write(f"✅ 기존 '리스트업' 워크시트 사용")
            except gspread.exceptions.WorksheetNotFound:
                st.write(f"✅ '리스트업' 워크시트 생성 중")
                email_worksheet = spreadsheet.add_worksheet(title="리스트업", rows=1000, cols=20)
                st.write(f"✅ '리스트업' 워크시트 생성 완료")
                
                # 헤더 설정 (순서 변경)
                email_headers = ["", "채널명", "유튜브 링크", "해당 채널 매칭 결과", "영업 이메일"]
                email_worksheet.update('A1:E1', [email_headers])
                st.write(f"✅ 헤더 설정 완료")
            
            # 이메일 데이터 준비
            email_rows = []
            st.write(f"✅ 이메일 데이터 처리 시작")
            
            for video_id, data in all_emails.items():
                if data.get('score', 0) >= 5.0:  # 8.5점 이상인 영상만 저장
                    # 해당 비디오 정보 찾기
                    video_info = next((v for v in recommended_videos if v.get('video_id') == video_id), {})
                    
                    # 매칭 결과에서 해당 비디오에 관한 부분만 추출
                    video_matching_result = extract_video_matching_result(matching_results, video_id)
                    
                    # 순서 변경: 빈칸, 채널명, 유튜브 링크, 매칭 결과, 영업 이메일
                    email_row = [
                        "",  # 첫 번째 열은 빈칸으로 설정
                        data.get('channel', ''),  # 채널명
                        video_info.get('url', ''),  # 유튜브 링크
                        video_matching_result,  # 해당 채널 매칭 결과
                        data.get('email', '')  # 영업 이메일
                    ]
                    email_rows.append(email_row)
            
            st.write(f"✅ 저장할 행 수: {len(email_rows)}개")
            
            # 빈 행이 있으면 데이터 추가
            if email_rows:
                # 마지막 행 번호 가져오기
                st.write(f"✅ 마지막 행 번호 가져오기")
                last_row = len(email_worksheet.get_all_values())
                if last_row == 0:
                    last_row = 1  # 헤더만 있는 경우
                st.write(f"✅ 마지막 행 번호: {last_row}")
                
                # 데이터 업데이트
                st.write(f"✅ 스프레드시트에 데이터 업데이트 시작: A{last_row+1}부터")
                email_worksheet.update(f'A{last_row+1}', email_rows)
                st.write(f"✅ 스프레드시트 데이터 업데이트 완료")
            else:
                st.write(f"⚠️ 저장할 데이터가 없습니다")
        else:
            st.write(f"⚠️ 이메일 데이터가 없어 스프레드시트에 저장하지 않습니다")
        
        return True, "스프레드시트에 데이터가 성공적으로 저장되었습니다."
        
    except Exception as e:
        error_message = f"스프레드시트 저장 중 오류 발생: {str(e)}"
        st.error(error_message)
        return False, error_message

# 매칭 결과에서 특정 비디오에 관한 부분만 추출하는 함수
def extract_video_matching_result(matching_results, video_id):
    """매칭 결과 텍스트에서 특정 비디오 ID에 관한 부분만 추출"""
    try:
        # 매칭 결과에서 영상 ID가 포함된 부분 찾기
        pattern = rf'\[{re.escape(video_id)}\].*?(?=\n\n\[|$)'
        match = re.search(pattern, matching_results, re.DOTALL)
        
        if match:
            # 추출된 부분 반환
            return match.group(0).strip()
        else:
            # 매치되는 부분이 없으면 비디오 ID만 반환
            return f"[{video_id}] 관련 매칭 결과를 찾을 수 없습니다."
    except Exception as e:
        return f"매칭 결과 추출 중 오류 발생: {str(e)}"
    

# 시트에서 키워드 목록을 읽어오는 함수
def get_keywords_from_sheet(spreadsheet_url):
    """Google 스프레드시트에서 키워드 목록을 가져옵니다."""
    try:
        st.write(f"✅ 키워드 목록을 시트에서 가져오는 중...")
        client = setup_google_sheets()
        
        # 스프레드시트 열기
        spreadsheet = client.open_by_url(spreadsheet_url)
        
        # 키워드 워크시트 찾기
        try:
            keyword_worksheet = spreadsheet.worksheet("키워드")
        except gspread.exceptions.WorksheetNotFound:
            # 키워드 시트가 없으면 새로 만듦
            keyword_worksheet = spreadsheet.add_worksheet(title="키워드", rows=1000, cols=2)
            # 헤더 추가
            keyword_worksheet.update('A1:B1', [["키워드", "실행 상태"]])
            st.warning("⚠️ '키워드' 시트가 없어 새로 생성했습니다. 키워드를 입력해주세요.")
            return []
        
        # 데이터 가져오기
        all_values = keyword_worksheet.get_all_values()
        
        # 헤더 제외하고 키워드 목록 추출 (첫 번째 열)
        if len(all_values) > 1:
            keywords = [row[0] for row in all_values[1:] if row[0].strip()]
            st.success(f"✅ {len(keywords)}개의 키워드를 시트에서 가져왔습니다.")
            return keywords
        else:
            st.warning("⚠️ 시트에 키워드가 없습니다.")
            return []
            
    except Exception as e:
        st.error(f"❌ 시트에서 키워드 목록을 가져오는 중 오류 발생: {str(e)}")
        return []

# 키워드의 실행 상태 업데이트 함수
def update_keyword_status(spreadsheet_url, keyword, status):
    """키워드의 실행 상태를 시트에 업데이트합니다."""
    try:
        client = setup_google_sheets()
        spreadsheet = client.open_by_url(spreadsheet_url)
        keyword_worksheet = spreadsheet.worksheet("키워드")
        
        # 키워드 찾기
        all_values = keyword_worksheet.get_all_values()
        for i, row in enumerate(all_values):
            if i == 0:  # 헤더 건너뛰기
                continue
            if row[0] == keyword:
                # 상태 업데이트 (B열)
                keyword_worksheet.update_cell(i+1, 2, status)
                st.write(f"✅ 키워드 '{keyword}'의 상태를 '{status}'로 업데이트했습니다.")
                break
                
    except Exception as e:
        st.error(f"❌ 키워드 상태 업데이트 중 오류 발생: {str(e)}")

# 여러 키워드를 자동으로 처리하는 함수
def run_batch_automation(spreadsheet_url, keywords, execution_count, max_videos, max_comments, max_videos_per_keyword, filter_duplicate_channels, min_subscribers):
    """지정된 개수의 키워드를 자동으로 처리합니다."""
    if not keywords:
        st.error("❌ 처리할 키워드가 없습니다.")
        return False
    
    # 실행할 키워드 수 제한
    keywords_to_process = keywords[:execution_count]
    st.write(f"🚀 {len(keywords_to_process)}개 키워드 자동 처리를 시작합니다: {keywords_to_process}")
    
    success_count = 0
    for i, keyword in enumerate(keywords_to_process):
        st.write(f"\n\n{'='*50}")
        st.subheader(f"키워드 {i+1}/{len(keywords_to_process)}: '{keyword}' 처리 중...")
        st.write(f"{'='*50}\n")
        
        # 키워드 처리 시작 상태 업데이트
        update_keyword_status(spreadsheet_url, keyword, "처리 중")
        
        try:
            # 단일 키워드 자동화 실행
            success = run_full_automation(
                keyword, 
                max_videos, 
                max_comments, 
                max_videos_per_keyword, 
                filter_duplicate_channels,
                min_subscribers,  # 최소 구독자 수 파라미터 추가
                spreadsheet_url
            )
            
            if success:
                success_count += 1
                update_keyword_status(spreadsheet_url, keyword, "완료")
            else:
                update_keyword_status(spreadsheet_url, keyword, "실패")
                
        except Exception as e:
            st.error(f"❌ 키워드 '{keyword}' 처리 중 오류 발생: {str(e)}")
            update_keyword_status(spreadsheet_url, keyword, f"오류: {str(e)[:50]}")
    
    st.success(f"🎉 배치 처리 완료: {success_count}/{len(keywords_to_process)}개 키워드 처리 성공")
    return success_count > 0


# YouTube API 클라이언트 설정
def get_youtube_client():
    api_service_name = "youtube"
    api_version = "v3"
    
    try:
        youtube = build(api_service_name, api_version, developerKey=YOUTUBE_API_KEY)
        return youtube
    except Exception as e:
        st.error(f"YouTube API 클라이언트 생성 실패: {str(e)}")
        return None

# Anthropic(Claude) 클라이언트 설정
def get_claude_client():
    return Anthropic(api_key=CLAUDE_API_KEY)

# 진행 상태 업데이트 함수
def update_progress(step, progress_within_step=0):
    st.session_state['current_step'] = step
    # 각 단계가 전체의 20%를 차지
    base_progress = step * 20
    step_progress = progress_within_step * 20  # 각 단계 내에서의 진행률 (0-20%)
    st.session_state['progress'] = base_progress + step_progress

# 진행 상태 표시 바
def show_progress_bar():
    current_step = st.session_state['current_step']
    steps = ["데이터 수집", "키워드 분석", "스크립트 수집", "콘텐츠 매칭", "영업 이메일 생성"]
    
    # 진행 상태 바
    st.progress(st.session_state['progress'] / 100)
    
    # 현재 단계 표시
    cols = st.columns(len(steps))
    for i, (col, step_name) in enumerate(zip(cols, steps)):
        if i < current_step:
            # 완료된 단계
            col.markdown(f"<div style='text-align: center; background-color: #4CAF50; color: white; padding: 10px; border-radius: 5px;'>{step_name} ✓</div>", unsafe_allow_html=True)
        elif i == current_step:
            # 현재 단계
            col.markdown(f"<div style='text-align: center; background-color: #2196F3; color: white; padding: 10px; border-radius: 5px;'>{step_name} 진행 중</div>", unsafe_allow_html=True)
        else:
            # 아직 시작하지 않은 단계
            col.markdown(f"<div style='text-align: center; background-color: #f0f0f0; padding: 10px; border-radius: 5px;'>{step_name}</div>", unsafe_allow_html=True)
    
    # 전체 진행률 표시
    st.caption(f"전체 진행률: {st.session_state['progress']}%")

# 1. 데이터 수집 함수들
def get_youtube_video_id(url):
    """유튜브 URL에서 동영상 ID 추출"""
    if "youtube.com/watch?v=" in url:
        return url.split("youtube.com/watch?v=")[1].split("&")[0]
    elif "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]
    return None

def get_top_videos_by_keyword(keyword, max_results=100, exclude_shorts=False, min_duration=0):
    st.write(f"✅ 키워드 '{keyword}'로 최대 {max_results}개 영상 검색 시작")
    
    videos = []
    next_page_token = None
    shorts_indicators = ["#shorts", "#short", "#Shorts", "#Short", "shorts", "Shorts", "쇼츠"]
    
    max_retries = 3
    
    try:
        # 요청된 결과 수에 도달하거나 더 이상 결과가 없을 때까지 반복
        while len(videos) < max_results:
            search_query = keyword
            if exclude_shorts:
                search_query = f"{keyword} -shorts"
            
            st.write(f"✅ YouTube API 요청 시작: 키워드='{search_query}', 페이지 토큰={next_page_token}")
            
            retry_count = 0
            success = False
            
            while retry_count < max_retries and not success:
                try:
                    youtube = get_youtube_client()
                    if not youtube:
                        st.error("YouTube API 클라이언트를 생성할 수 없습니다.")
                        return videos
                        
                    search_params = {
                        'q': search_query,
                        'part': "id,snippet",
                        'maxResults': min(50, max_results - len(videos) + 20),
                        'type': "video",
                        'relevanceLanguage': "ko"
                    }
                    
                    if next_page_token:
                        search_params['pageToken'] = next_page_token
                        
                    search_response = youtube.search().list(**search_params).execute()
                    success = True
                
                except Exception as e:
                    retry_count += 1
                    st.error(f"API 요청 오류: {str(e)}. 재시도 중... ({retry_count}/{max_retries})")
                    time.sleep(2)  # 잠시 대기 후 재시도
                    if retry_count >= max_retries:
                        st.error("최대 재시도 횟수 초과")
                        return videos
            
            # 검색된 비디오 ID 목록
            video_ids = [item["id"]["videoId"] for item in search_response.get("items", []) 
                        if item["id"]["kind"] == "youtube#video"]
            
            if not video_ids:
                break
                
            # 비디오 세부 정보 일괄 가져오기 (길이 확인용)
            retry_count = 0
            video_details_success = False
            
            while retry_count < max_retries and not video_details_success:
                try:
                    video_details_response = youtube.videos().list(
                        part="snippet,contentDetails",
                        id=",".join(video_ids)
                    ).execute()
                    
                    video_details_success = True
                    
                    # 결과 처리 및 필터링
                    for item in video_details_response.get("items", []):
                        video_id = item["id"]
                        snippet = item["snippet"]
                        title = snippet["title"]
                        description = snippet.get("description", "")
                        channel_name = snippet["channelTitle"]
                        
                        # 숏츠 필터링
                        if exclude_shorts and (any(indicator in title for indicator in shorts_indicators) or 
                                            any(indicator in description for indicator in shorts_indicators)):
                            st.write(f"⚠️ 숏츠로 판단되는 영상 건너뛰기: '{title}'")
                            continue
                        
                        # 영상 길이 확인 (ISO 8601 형식)
                        duration = item["contentDetails"]["duration"]
                        import re
                        duration_match = re.match(r'PT(\d+H)?(\d+M)?(\d+S)?', duration)
                        if duration_match:
                            hours = int(duration_match.group(1)[:-1]) if duration_match.group(1) else 0
                            minutes = int(duration_match.group(2)[:-1]) if duration_match.group(2) else 0
                            seconds = int(duration_match.group(3)[:-1]) if duration_match.group(3) else 0
                            total_seconds = hours * 3600 + minutes * 60 + seconds
                            
                            # 최소 길이 필터링
                            if min_duration > 0 and total_seconds < min_duration:
                                st.write(f"⚠️ 영상 길이가 너무 짧아 제외됨: '{title}' ({total_seconds}초)")
                                continue
                        
                        videos.append({
                            "video_id": video_id,
                            "title": title,
                            "channel_name": channel_name
                        })
                        
                        if len(videos) >= max_results:
                            break
                
                except Exception as e:
                    retry_count += 1
                    st.error(f"비디오 세부 정보 요청 오류: {str(e)}. 재시도 중... ({retry_count}/{max_retries})")
                    time.sleep(2)
                    if retry_count >= max_retries:
                        break
            
            # 다음 페이지 토큰 확인
            next_page_token = search_response.get("nextPageToken")
            if not next_page_token or len(videos) >= max_results:
                break
                
            time.sleep(0.5)
        
        st.write(f"✅ 검색 결과: {len(videos)}개 영상 찾음 (최소 길이 {min_duration}초 이상)")
        return videos
        
    except Exception as e:
        st.error(f"❌ 유튜브 영상 검색 중 오류 발생: {str(e)}")
        st.exception(e)
        return videos

def get_video_comments(video_id, max_comments=20):
    """영상의 댓글 가져오기 (좋아요 많은 순)"""
    youtube = get_youtube_client()
    
    try:
        comments = []
        request = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=max_comments,
            order="relevance"  # 관련성(좋아요 많은 순) 기준
        )
        response = request.execute()
        
        for item in response["items"]:
            comment = item["snippet"]["topLevelComment"]["snippet"]
            comments.append({
                "text": comment["textDisplay"],
                "author": comment["authorDisplayName"],
                "likes": comment["likeCount"],
                "published_at": comment["publishedAt"],
                "video_id": video_id
            })
        return comments
    except Exception as e:
        error_message = str(e)
        # 이 부분을 except 블록 내부로 이동
        if "disabled comments" in error_message:
            st.warning(f"영상 '{video_id}'의 댓글이 비활성화되어 있어 수집할 수 없습니다.")
        else:
            st.error(f"댓글 수집 중 오류 발생: {error_message}")
        return []


def collect_comments_by_keyword(keyword, max_videos=5, max_comments=20):
    """키워드로 검색해 상위 영상들의 댓글 수집"""
    update_progress(0, 0.2)  # 진행 상태 20%
    
    videos = get_top_videos_by_keyword(keyword, max_videos, exclude_shorts=False, min_duration=0) # 숏츠 제외
    
    update_progress(0, 0.4)  # 진행 상태 40%
    
    all_comments = []
    disabled_comments_count = 0  # 댓글이 비활성화된 영상 카운트
    
    for i, video in enumerate(videos):
        progress = 0.4 + (0.6 * (i / len(videos)))  # 40%~100% 사이에서 진행
        update_progress(0, progress)
        
        video_comments = get_video_comments(video["video_id"], max_comments)
        if not video_comments:
            disabled_comments_count += 1  # 댓글 없는 경우 카운트 증가
        
        for comment in video_comments:
            comment["video_title"] = video["title"]
            comment["channel_name"] = video["channel_name"]
        all_comments.extend(video_comments)
    
    update_progress(0, 1.0)  # 이 단계 완료
    
    # 결과 요약 메시지 출력
    if disabled_comments_count > 0:
        st.info(f"{len(videos)}개 영상 중 {disabled_comments_count}개 영상은 댓글이 비활성화되어 있거나 수집 중 오류가 발생했습니다.")
    
    return all_comments

def collect_comments_by_url(url, max_comments=20):
    """유튜브 URL로 해당 영상의 댓글만 수집"""
    update_progress(0, 0.3)  # 진행 상태 30%
    
    video_id = get_youtube_video_id(url)
    if not video_id:
        st.error("올바른 유튜브 URL이 아닙니다.")
        return []
    
    update_progress(0, 0.6)  # 진행 상태 60%
    
    # 영상 정보 가져오기
    youtube = get_youtube_client()
    try:
        video_response = youtube.videos().list(
            part="snippet",
            id=video_id
        ).execute()
        
        if not video_response.get("items"):
            st.error("영상 정보를 찾을 수 없습니다.")
            return []
        
        video_info = video_response["items"][0]["snippet"]
        title = video_info["title"]
        channel_name = video_info["channelTitle"]
        
        # 댓글 수집
        comments = get_video_comments(video_id, max_comments)
        for comment in comments:
            comment["video_title"] = title
            comment["channel_name"] = channel_name
        
        update_progress(0, 1.0)  # 이 단계 완료
        return comments
    except Exception as e:
        st.error(f"영상 정보 수집 중 오류 발생: {str(e)}")
        return []

def parse_csv_comments(uploaded_file):
    """업로드된 CSV 파일에서 댓글 데이터 파싱"""
    update_progress(0, 0.5)  # 진행 상태 50%
    
    try:
        df = pd.read_csv(uploaded_file)
        comments = []
        
        # CSV 파일의 형식에 따라 조정 필요
        required_columns = ["text"]  # 최소한 댓글 내용은 필요
        
        # 필수 컬럼 확인
        for col in required_columns:
            if col not in df.columns:
                st.error(f"CSV 파일에 필수 컬럼이 없습니다: {col}")
                return []
        
        # CSV 데이터를 댓글 형식으로 변환
        for _, row in df.iterrows():
            comment = {
                "text": row["text"],
                "author": row.get("author", "Unknown"),
                "likes": row.get("likes", 0),
                "published_at": row.get("published_at", ""),
                "video_id": row.get("video_id", ""),
                "video_title": row.get("video_title", ""),
                "channel_name": row.get("channel_name", "")
            }
            comments.append(comment)
        
        update_progress(0, 1.0)  # 이 단계 완료
        return comments
    except Exception as e:
        st.error(f"CSV 파일 파싱 중 오류 발생: {str(e)}")
        return []

def analyze_comments_with_claude(comments_data, search_keyword=""):
    """Claude API를 사용해 댓글 데이터 분석"""
    update_progress(1, 0.3)  # 진행 상태 30%
    
    client = get_claude_client()
    
    # 댓글 데이터를 문자열로 변환
    comments_text = "\n\n".join([comment["text"] for comment in comments_data])
    
    # 인사이터 프롬프트 준비
    with open("insighter_prompt.txt", "r", encoding="utf-8") as f:
        prompt_template = f.read()
    
    # 검색 키워드와 댓글 데이터를 프롬프트에 삽입
    prompt = prompt_template.replace("{{INITIAL_SEARCH_KEYWORD}}", search_keyword)
    prompt = prompt.replace("{{COMMENTS_DATA}}", comments_text)
    
    try:
        response = client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=8000,
            temperature=0.5,
            system="당신은 댓글 데이터를 분석하여 사용자들의 심리적 결핍과 집착 패턴을 파악하고, 이를 바탕으로 핵심 키워드를 추출하는 전문가입니다.",
            messages=[{"role": "user", "content": prompt}]
        )
        
        analysis_result = response.content[0].text
        update_progress(1, 1.0)  # 이 단계 완료
        return analysis_result
    except Exception as e:
        st.error(f"Claude API 호출 중 오류 발생: {str(e)}")
        return None
    

        
def extract_structured_data_from_analysis(analysis_text):
    """분석 텍스트에서 구조화된 데이터 추출"""
    # 실제 구현에서는 정규식 또는 다른 파싱 로직을 사용할 수 있음
    # 여기서는 단순화를 위해 전체 텍스트를 반환
    return {
        "raw_text": analysis_text,
        "keywords": extract_keywords(analysis_text),
        "deficiency_solution_pairs": extract_deficiency_solution_pairs(analysis_text),
        "message_framework": extract_message_framework(analysis_text)
    }

def extract_keywords(analysis_text):
    """분석 텍스트에서 키워드 추출"""
    # 실제 구현에서는 더 정교한 파싱 로직 필요
    keywords = []
    # 예시 추출 로직 (실제 구현 필요)
    if "핵심 키워드" in analysis_text:
        keywords_section = analysis_text.split("핵심 키워드")[1].split("결핍-솔루션 페어")[0]
        # 더 정교한 파싱 필요
    return keywords

def extract_deficiency_solution_pairs(analysis_text):
    """분석 텍스트에서 결핍-솔루션 페어 추출"""
    # 실제 구현에서는 더 정교한 파싱 로직 필요
    pairs = []
    # 예시 추출 로직 (실제 구현 필요)
    if "결핍-솔루션 페어" in analysis_text:
        pairs_section = analysis_text.split("결핍-솔루션 페어")[1].split("메시지 프레임워크")[0]
        # 더 정교한 파싱 필요
    return pairs

def extract_message_framework(analysis_text):
    """분석 텍스트에서 메시지 프레임워크 추출"""
    # 실제 구현에서는 더 정교한 파싱 로직 필요
    framework = []
    # 예시 추출 로직 (실제 구현 필요)
    if "메시지 프레임워크" in analysis_text:
        framework_section = analysis_text.split("메시지 프레임워크")[1]
        # 더 정교한 파싱 필요
    return framework

# 3. 스크립트 수집 함수들
def get_video_transcript(video_id):
    """유튜브 영상의 스크립트(자막) 가져오기"""
    st.write(f"✅ 영상 ID '{video_id}'의 스크립트 수집 시작")
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        st.write(f"✅ YouTubeTranscriptApi 요청 시작")
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko'])
        full_transcript = " ".join([entry['text'] for entry in transcript_list])
        st.write(f"✅ 스크립트 수집 완료: {len(full_transcript)} 글자")
        return full_transcript
    except Exception as e:
        st.warning(f"⚠️ 스크립트 수집 중 오류 발생: {str(e)}")
        return None
    
def collect_scripts_parallel(videos, max_videos_per_keyword, filter_duplicate_channels, collected_channels, min_duration_seconds, max_duration_seconds, max_age_days, min_subscribers, max_workers=5):
    """여러 영상의 정보와 스크립트를 병렬로 수집"""
    results = []
    successful_count = 0
    
    # 상태 표시 변수
    completed = 0
    total = len(videos)
    
    def process_video(video):
        video_id = video["video_id"]
        channel_name = video["channel_name"]
        
        # 중복 채널 필터링
        if filter_duplicate_channels and channel_name in collected_channels:
            return None
            
        # 영상 상세 정보 가져오기
        video_details = get_video_details(
            video_id, 
            min_duration_seconds, 
            max_duration_seconds, 
            max_age_days,
            min_subscribers
        )
        
        if not video_details:
            return None
            
        # 스크립트 가져오기
        transcript = get_video_transcript(video_id)
        
        if transcript:
            video_details["script"] = transcript
            return video_details
        
        return None
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 여러 영상을 병렬로 처리
        future_to_video = {executor.submit(process_video, video): video for video in videos}
        
        # 완료된 작업 결과 수집
        for future in concurrent.futures.as_completed(future_to_video):
            completed += 1
            
            # st.empty() 사용 대신 직접 상태 출력
            st.write(f"병렬 처리 중: {completed}/{total} 완료 (성공: {successful_count}개)")
            
            try:
                result = future.result()
                if result:  # 유효한 결과만 추가
                    results.append(result)
                    collected_channels.add(result['channel_name'])
                    successful_count += 1
                    
                    # 이미 충분한 영상을 수집했으면 종료
                    if len(results) >= max_videos_per_keyword:
                        break
            except Exception as e:
                video = future_to_video[future]
                st.warning(f"영상 '{video['title']}' 처리 중 오류: {str(e)}")
    
    return results
    
    def process_video(video):
        video_id = video["video_id"]
        channel_name = video["channel_name"]
        
        # 중복 채널 필터링
        if filter_duplicate_channels and channel_name in collected_channels:
            return None
            
        # 영상 상세 정보 가져오기
        video_details = get_video_details(
            video_id, 
            min_duration_seconds, 
            max_duration_seconds, 
            max_age_days,
            min_subscribers
        )
        
        if not video_details:
            return None
            
        # 스크립트 가져오기
        transcript = get_video_transcript(video_id)
        
        if transcript:
            video_details["script"] = transcript
            return video_details
        
        return None
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 여러 영상을 병렬로 처리
        future_to_video = {executor.submit(process_video, video): video for video in videos}
        
        with st.empty() as status_container:
            completed = 0
            total = len(videos)
            
            # 완료된 작업 결과 수집
            for future in concurrent.futures.as_completed(future_to_video):
                completed += 1
                status_container.text(f"병렬 처리 중: {completed}/{total} 완료 (성공: {successful_count}개)")
                
                try:
                    result = future.result()
                    if result:  # 유효한 결과만 추가
                        results.append(result)
                        collected_channels.add(result['channel_name'])
                        successful_count += 1
                        
                        # 이미 충분한 영상을 수집했으면 종료
                        if len(results) >= max_videos_per_keyword:
                            break
                except Exception as e:
                    video = future_to_video[future]
                    st.warning(f"영상 '{video['title']}' 처리 중 오류: {str(e)}")
    
    return results

def get_channel_details(channel_id):
    """유튜브 채널의 상세 정보(구독자 수 등) 가져오기"""
    st.write(f"✅ 채널 ID '{channel_id}'의 상세 정보 수집 시작")
    
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            youtube = get_youtube_client()
            if not youtube:
                st.error("YouTube API 클라이언트를 생성할 수 없습니다.")
                return None
                
            st.write(f"✅ YouTube API 요청 시작: channel_id='{channel_id}'")
            channel_response = youtube.channels().list(
                part="snippet,statistics",
                id=channel_id
            ).execute()
            
            if not channel_response.get("items"):
                st.warning(f"⚠️ 채널 ID '{channel_id}'의 정보를 찾을 수 없음")
                return None
            
            channel_info = channel_response["items"][0]
            statistics = channel_info["statistics"]
            
            # 구독자 수 가져오기 (비공개인 경우 0으로 처리)
            subscriber_count = int(statistics.get("subscriberCount", 0))
            
            st.write(f"✅ 채널 정보 수집 완료: 구독자 수 {subscriber_count}명")
            
            return {
                "channel_id": channel_id,
                "subscriber_count": subscriber_count
            }
            
        except Exception as e:
            retry_count += 1
            st.error(f"채널 정보 요청 오류: {str(e)}. 재시도 중... ({retry_count}/{max_retries})")
            time.sleep(2)  # 잠시 대기 후 재시도
            if retry_count >= max_retries:
                st.error(f"최대 재시도 횟수({max_retries})를 초과했습니다.")
                return None
    
    return None

def get_channels_details_parallel(channel_ids, max_workers=5):
    """여러 채널의 정보를 병렬로 수집"""
    results = {}
    
    def process_channel(channel_id):
        return (channel_id, get_channel_details(channel_id))
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 여러 채널을 병렬로 처리
        future_to_channel = {executor.submit(process_channel, cid): cid for cid in channel_ids}
        
        # 완료된 작업 결과 수집
        for future in concurrent.futures.as_completed(future_to_channel):
            try:
                channel_id, result = future.result()
                if result:  # 유효한 결과만 추가
                    results[channel_id] = result
            except Exception as e:
                channel_id = future_to_channel[future]
                st.warning(f"채널 ID {channel_id} 처리 중 오류: {str(e)}")
    
    return results



def get_video_details(video_id, min_duration_seconds=180, max_duration_seconds=1800, max_age_days=730, min_subscribers=5000):
    st.write(f"✅ 영상 ID '{video_id}'의 상세 정보 수집 시작")
    
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            youtube = get_youtube_client()
            if not youtube:
                st.error("YouTube API 클라이언트를 생성할 수 없습니다.")
                return None
                
            st.write(f"✅ YouTube API 요청 시작: video_id='{video_id}'")
            video_response = youtube.videos().list(
                part="snippet,statistics,contentDetails",
                id=video_id
            ).execute()
            
            if not video_response.get("items"):
                st.warning(f"⚠️ 영상 ID '{video_id}'의 정보를 찾을 수 없음")
                return None
            
            video_info = video_response["items"][0]
            snippet = video_info["snippet"]
            statistics = video_info["statistics"]
            content_details = video_info["contentDetails"]
            
            # 채널명 및 제목 가져오기
            channel_name = snippet["channelTitle"]
            title = snippet["title"]
            description = snippet["description"]
            category_id = snippet.get("categoryId", "")
            
            # 채널 ID 가져오기
            channel_id = snippet["channelId"]
            
            # 채널 정보 가져오기
            channel_details = get_channel_details(channel_id)
            
            if channel_details:
                # 구독자 수 확인
                subscriber_count = channel_details["subscriber_count"]
                
                # 구독자 수가 최소 구독자 수보다 적으면 필터링
                if subscriber_count < min_subscribers:
                    st.write(f"⚠️ 영상 ID '{video_id}'의 채널 구독자 수({subscriber_count}명)가 최소 기준({min_subscribers}명)보다 적어 제외됩니다.")
                    return None
                
                # 구독자 수 정보 추가
                video_details = {
                    "subscriber_count": subscriber_count
                }
            
            # 업로드 날짜 확인
            from datetime import datetime, timezone
            published_at = snippet["publishedAt"]
            published_date = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
            current_date = datetime.now(timezone.utc)
            days_since_published = (current_date - published_date).days
            
            # 업로드 날짜 필터링만 유지
            if max_age_days > 0 and days_since_published > max_age_days:
                st.write(f"⚠️ 영상 ID '{video_id}'는 업로드 기간이 너무 오래되어 제외됩니다(업로드 후 {days_since_published}일).")
                return None
            
            # 영상 길이 확인 (길이 제한 적용)
            duration = content_details.get("duration", "")
            if duration:
                # ISO 8601 형식의 duration을 초 단위로 변환
                import re
                duration_match = re.match(r'PT(\d+H)?(\d+M)?(\d+S)?', duration)
                if duration_match:
                    hours = int(duration_match.group(1)[:-1]) if duration_match.group(1) else 0
                    minutes = int(duration_match.group(2)[:-1]) if duration_match.group(2) else 0
                    seconds = int(duration_match.group(3)[:-1]) if duration_match.group(3) else 0
                    
                    total_seconds = hours * 3600 + minutes * 60 + seconds
                    
                    if total_seconds < min_duration_seconds:
                        st.write(f"⚠️ 영상 ID '{video_id}'는 길이가 너무 짧아 제외됩니다 ({total_seconds}초, 최소 {min_duration_seconds}초).")
                        return None
                        
                    if max_duration_seconds > 0 and total_seconds > max_duration_seconds:
                        st.write(f"⚠️ 영상 ID '{video_id}'는 길이가 너무 길어 제외됩니다 ({total_seconds}초, 최대 {max_duration_seconds}초).")
                        return None
            
            # 조회수 및 좋아요 수 가져오기
            view_count = int(statistics.get("viewCount", 0))
            like_count = int(statistics.get("likeCount", 0))
            
            # 영상 정보 반환
            video_details = {
                "video_id": video_id,
                "title": title,
                "channel_name": channel_name,
                "channel_id": channel_id,
                "description": description,
                "view_count": view_count,
                "like_count": like_count,
                "published_at": published_at,
                "duration_seconds": total_seconds if 'total_seconds' in locals() else 0,
                "category_id": category_id,
                "video_link": f"https://www.youtube.com/watch?v={video_id}",
                "subscriber_count": subscriber_count if 'subscriber_count' in locals() else 0
            }
            
            st.write(f"✅ 영상 상세 정보 수집 완료: {title}")
            return video_details
            
        except Exception as e:
            retry_count += 1
            st.error(f"영상 정보 요청 오류: {str(e)}. 재시도 중... ({retry_count}/{max_retries})")
            time.sleep(2)  # 잠시 대기 후 재시도
            if retry_count >= max_retries:
                st.error(f"최대 재시도 횟수({max_retries})를 초과했습니다.")
                return None
    
    return None

def collect_scripts_by_keywords(keywords, max_videos_per_keyword=3, filter_duplicate_channels=True, min_duration_seconds=180, max_duration_seconds=1800, max_age_days=1000, min_subscribers=5000, spreadsheet_url=None):
    """키워드 리스트로 영상 검색 및 스크립트 수집 (병렬 처리 적용)"""
    st.write(f"✅ 스크립트 수집 시작: {len(keywords)}개 키워드, 키워드당 {max_videos_per_keyword}개 영상, 최소 구독자 수: {min_subscribers}명")
    st.write(f"✅ 처리할 키워드: {keywords}")
    update_progress(2, 0.1)  # 진행 상태 10%
    
    all_scripts = []
    collected_channels = set()  # 이미 수집한 채널 추적
    
    # 스프레드시트에서 이미 수집된 채널 가져오기
    if spreadsheet_url and filter_duplicate_channels:
        st.write("✅ 스프레드시트에서 이미 수집된 채널 확인 중...")
        sheet_channels = get_collected_channels_from_sheet(spreadsheet_url)
        if sheet_channels:
            collected_channels.update(sheet_channels)
            st.write(f"✅ 스프레드시트에서 {len(sheet_channels)}개 채널을 가져와 중복 필터링에 적용합니다.")
    
    # 병렬 처리 워커 수 설정 (고정값 사용)
    max_workers = 3  # 적절한 고정값으로 설정
    st.write(f"✅ 병렬 처리 워커 수: {max_workers}개")
    
    for i, keyword in enumerate(keywords):
        progress = 0.1 + (0.9 * (i / len(keywords)))  # 10%~100% 사이에서 진행
        update_progress(2, progress)
        
        st.write(f"✅ 키워드 {i+1}/{len(keywords)} 처리 중: '{keyword}'")
        
        # 최대 150개 영상 검색
        max_search_results = 150
        videos = get_top_videos_by_keyword(keyword, max_search_results, exclude_shorts=True, min_duration=180)
        st.write(f"✅ 키워드 '{keyword}'로 {len(videos)}개 영상 찾음")
        
        if not videos:
            st.warning(f"⚠️ 키워드 '{keyword}'로 영상을 찾지 못했습니다.")
            continue
        
        # 병렬 처리로 스크립트 수집
        keyword_scripts = collect_scripts_parallel(
            videos, 
            max_videos_per_keyword, 
            filter_duplicate_channels, 
            collected_channels,
            min_duration_seconds,
            max_duration_seconds,
            max_age_days,
            min_subscribers,
            max_workers=max_workers
        )
        
        all_scripts.extend(keyword_scripts)
        
        st.write(f"✅ 키워드 '{keyword}'에 대해 {len(keyword_scripts)}/{max_videos_per_keyword}개 영상 수집됨")
    
    st.write(f"✅ 전체 수집 완료: {len(all_scripts)}개 영상의 스크립트 수집됨")
    st.write(f"✅ 수집된 채널 수: {len(collected_channels)}개")
    update_progress(2, 1.0)  # 이 단계 완료
    return all_scripts

def extract_recommended_videos(matching_text):
    """매칭 결과에서 추천 영상 정보 추출 (개선된 버전)"""
    st.write("✅ 매칭 결과에서 추천 영상 추출 시작")
    recommended_videos = []  # 추천 영상 정보를 저장할 리스트 초기화
    
    try:
        # 최종 추천 영상 섹션 찾기
        if "최종 추천 영상" in matching_text:
            recommended_section = matching_text.split("최종 추천 영상")[1]
            st.write("✅ 최종 추천 영상 섹션 발견")
            
            # 추천 영상 패턴 정규식 - 영상 ID, 제목, 점수 찾기
            pattern = r'\[([^\]]+)\]\s*-\s*([^-]+)-\s*종합\s*점수:\s*(\d+\.?\d*)\/10'
            matches = re.findall(pattern, recommended_section)
            
            st.write(f"✅ 추천 영상 패턴 검색 결과: {len(matches)}개 발견")
            
            for i, match in enumerate(matches, 1):
                video_id = match[0].strip()
                title = match[1].strip()
                score = float(match[2])
                
                st.write(f"✅ 영상 {i} 발견: '{title}', ID: {video_id}, 점수: {score}/10")
                
                # 채널명 찾기
                channel_pattern = fr'링크: https://www\.youtube\.com/watch\?v={re.escape(video_id)}[^\n]*\n\*\s*채널:\s*([^\n]+)'
                channel_match = re.search(channel_pattern, matching_text)
                channel = channel_match.group(1).strip() if channel_match else "Unknown"
                
                # 콘텐츠 유형 찾기 - 여기가 문제의 원인
                content_type_pattern = fr'콘텐츠 유형:\s*([^\n]+)'
                content_type_match = re.search(content_type_pattern, matching_text)
                content_type = content_type_match.group(1).strip() if content_type_match else "Unknown"
                
                # 추천 영상 추가
                recommended_videos.append({
                    "rank": i,
                    "title": title,
                    "channel": channel,
                    "score": score,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "video_id": video_id,
                    "content_type": content_type  # 여기서 정의된 변수 사용
                })
                
                st.write(f"✅ 추천 영상으로 추가됨: '{title}', 점수: {score}/10")
        else:
            # 기존 패턴으로 시도 - 영상별 분석 패턴
            st.write("⚠️ 최종 추천 영상 섹션이 없습니다. 일반 패턴으로 검색합니다.")
            pattern = r'영상 \d+: (.*?)\n.*?채널명: (.*?)\n.*?링크: (https://www\.youtube\.com/watch\?v=([^\s\n]+)).*?관련성 점수: (\d+)\/10'
            matches = re.findall(pattern, matching_text, re.DOTALL)
            
            for i, match in enumerate(matches, 1):
                title = match[0].strip()
                channel = match[1].strip()
                url = match[2].strip()
                video_id = match[3].strip()
                score = float(match[4])
                
                st.write(f"✅ 영상 발견: '{title}', 점수: {score}/10")
                
                # 영상 추가
                recommended_videos.append({
                    "rank": i,
                    "title": title,
                    "url": url,
                    "channel": channel,
                    "score": score,
                    "video_id": video_id,
                    "content_type": "Unknown"  # 기본값 설정
                })
                
                # 8.5점 이상인 경우 로그 표시
                if score >= 5.0:
                    st.write(f"✅ 추천 영상으로 선택됨: '{title}', 점수: {score}/10")
        
        # 점수 순으로 정렬
        recommended_videos.sort(key=lambda x: x["score"], reverse=True)
        
        if not recommended_videos:
            st.write("⚠️ 영상을 찾지 못했습니다.")
        else:
            st.write(f"✅ 총 {len(recommended_videos)}개의 영상을 발견했습니다.")
            recommended_count = len([v for v in recommended_videos if v["score"] >= 5.0])
            st.write(f"✅ 그 중 5.0점 이상 추천 영상: {recommended_count}개")
    
    except Exception as e:
        st.error(f"❌ 추천 영상 추출 중 오류 발생: {str(e)}")
        st.exception(e)  # 상세 오류 출력
    
    return recommended_videos

def extract_batch_recommendations(batch_result):
    """배치 결과에서 추천 영상 정보 추출"""
    recommendations = []
    
    try:
        # 추천 영상 패턴 정규식
        if "최종 추천 영상" in batch_result:
            # 영상 ID - 제목 - 종합 점수 패턴 찾기
            pattern = r'\[([^\]]+)\]\s*-\s*([^-]+)-\s*종합\s*점수:\s*(\d+\.?\d*)\/10'
            matches = re.findall(pattern, batch_result)
            
            for match in matches:
                video_id = match[0].strip()
                title = match[1].strip()
                score = float(match[2])
                
                # 각 영상 ID에 대한 전체 섹션 추출
                section_start = batch_result.find(f"[{video_id}]")
                if section_start == -1:
                    continue
                
                next_video_start = batch_result.find("[", section_start + 1)
                if next_video_start == -1:
                    video_section = batch_result[section_start:]
                else:
                    video_section = batch_result[section_start:next_video_start]
                
                # 채널명 찾기
                channel_pattern = r'채널:\s*([^\n]+)'
                channel_match = re.search(channel_pattern, video_section)
                channel = channel_match.group(1).strip() if channel_match else "Unknown"
                
                # 콘텐츠 유형 찾기
                content_type_pattern = r'콘텐츠 유형:\s*([^\n]+)'
                content_type_match = re.search(content_type_pattern, video_section)
                content_type = content_type_match.group(1).strip() if content_type_match else "Unknown"
                
                # 주요 키워드 찾기
                keywords_pattern = r'주요 키워드:\s*([^\n]+)'
                keywords_match = re.search(keywords_pattern, video_section)
                keywords = keywords_match.group(1).strip() if keywords_match else ""
                
                # 교육 콘텐츠 점수와 교육자 점수 찾기 - 실제 출력에 맞게 패턴 수정
                # 다양한 패턴을 시도하여 매칭
                scores_patterns = [
                    r'교육 콘텐츠 점수:\s*(\d+\.?\d*)\/10\s*\|\s*교육자 점수:\s*(\d+\.?\d*)\/10',
                    r'교육 콘텐츠 점수:\s*(\d+\.?\d*)\/10\s*\|\s*교육자\/경험 전달자 점수:\s*(\d+\.?\d*)\/10',
                    r'교육 콘텐츠 점수:\s*(\d+\.?\d*)\/10\s*\|\s*경험 전달자 점수:\s*(\d+\.?\d*)\/10',
                    r'교육 콘텐츠 점수:\s*(\d+\.?\d*)\/10\s*\|\s*[^:]+점수:\s*(\d+\.?\d*)\/10',
                    r'교육 콘텐츠 점수:\s*(\d+\.?\d*)\/10\s*\|\s*교육자 특성 점수:\s*(\d+\.?\d*)\/10'
                ]
                
                educational_score = 0
                teacher_score = 0
                found_scores = False
                
                for pattern in scores_patterns:
                    scores_match = re.search(pattern, video_section)
                    if scores_match:
                        educational_score = float(scores_match.group(1))
                        teacher_score = float(scores_match.group(2))
                        found_scores = True
                        break
                
                if not found_scores:
                    continue
                
                # 키워드 매칭, 발화 유사성, 결핍-솔루션 점수 찾기
                detail_pattern = r'키워드 매칭:\s*(\d+\.?\d*)\/10\s*\|\s*발화 유사성:\s*(\d+)%\s*\|\s*결핍-솔루션:\s*(\d+\.?\d*)\/10'
                detail_match = re.search(detail_pattern, video_section)
                
                if detail_match:
                    keyword_score = float(detail_match.group(1))
                    similarity_score = int(detail_match.group(2))
                    deficiency_score = float(detail_match.group(3))
                else:
                    continue
                
                # 주요 결핍 유형 찾기
                deficiency_pattern = r'주요 결핍 유형:\s*([^\n]+)'
                deficiency_match = re.search(deficiency_pattern, video_section)
                deficiency_types = deficiency_match.group(1).strip() if deficiency_match else ""
                
                # 인사이트 섹션 찾기
                insight_pattern = r'<인사이트>\n(.*?)(?=\n\n|\Z)'
                insight_match = re.search(insight_pattern, video_section, re.DOTALL)
                insight = insight_match.group(1).strip() if insight_match else ""
                
                recommendations.append({
                    "video_id": video_id,
                    "title": title,
                    "channel": channel,
                    "score": score,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "content_type": content_type,
                    "keywords": keywords,
                    "educational_score": educational_score,
                    "teacher_score": teacher_score,
                    "keyword_score": keyword_score,
                    "similarity_score": similarity_score,
                    "deficiency_score": deficiency_score,
                    "deficiency_types": deficiency_types,
                    "insight": insight
                })
        
        return recommendations
    except Exception as e:
        st.error(f"추천 영상 추출 중 오류 발생: {str(e)}")
        return []
    
def format_final_recommendations(recommendations):
    """추천 영상 정보를 최종 결과 포맷으로 변환"""
    formatted_text = ""
    
    # 8.5점 이상 영상만 필터링
    high_score_recommendations = [r for r in recommendations if r.get("score", 0) >= 5.0]
    
    for i, rec in enumerate(high_score_recommendations, 1):
        formatted_text += f"""
[{rec['video_id']}] - {rec['title']} - 종합 점수: {rec['score']}/10
* 링크: {rec['url']}
* 채널: {rec['channel']}
* 주요 키워드: {rec.get('keywords', '정보 없음')}
* 교육 콘텐츠 점수: {rec.get('educational_score', 0)}/10 | 교육자/경험 전달자 점수: {rec.get('teacher_score', 0)}/10
* 키워드 매칭: {rec.get('keyword_score', 0)}/10 | 발화 유사성: {rec.get('similarity_score', 0)}% | 결핍-솔루션: {rec.get('deficiency_score', 0)}/10
* 주요 결핍 유형: {rec.get('deficiency_types', '정보 없음')}

<인사이트>
{rec.get('insight', '추가 분석 정보 없음')}

"""
    
    if not high_score_recommendations:
        formatted_text = "5.0점 이상의 추천 영상이 없습니다."
    
    return formatted_text

# 기존 함수를 새 버전으로 교체
def match_content_with_claude(keywords_analysis, scripts_data, batch_size=2, max_workers=3):
    """Claude API를 사용해 키워드와 스크립트 매칭 분석 (병렬 처리 적용)"""
    update_progress(3, 0.1)  # 진행 상태 10%
    
    client = get_claude_client()
    
    # 매칭 프롬프트 준비
    with open("matching_prompt.txt", "r", encoding="utf-8") as f:
        prompt_template = f.read()
    
    # 키워드 분석 데이터 준비
    keywords_data = keywords_analysis.get("raw_text", "")
    
    # 스크립트를 batch_size 크기의 그룹으로 나누기
    script_batches = [scripts_data[i:i+batch_size] for i in range(0, len(scripts_data), batch_size)]
    st.write(f"✅ 스크립트를 {len(script_batches)}개 배치로 나눠서 처리합니다 (배치당 최대 {batch_size}개)")
    
    # 병렬 처리 시작
    batch_results = []
    completed = 0
    total = len(script_batches)
    
    # 배치들을 max_workers 개씩 병렬로 처리
    for i in range(0, total, max_workers):
        current_batch_indices = list(range(i, min(i + max_workers, total)))
        st.write(f"🔄 {len(current_batch_indices)}개 배치 병렬 처리 시작 (배치 {i+1}~{min(i+max_workers, total)}/{total})")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 배치 처리 함수 정의
            def process_batch(batch_index):
                batch = script_batches[batch_index]
                
                # 배치의 스크립트 데이터 준비
                scripts_text = ""
                for script in batch:
                    scripts_text += f"""
                    **영상 ID**: {script['video_id']}
                    **채널명**: {script['channel_name']}
                    **영상 제목**: {script['title']}
                    **카테고리**: {script.get('category_id', 'Unknown')}
                    **영상 링크**: {script['video_link']}
                    **조회수**: {script.get('view_count', 0)}
                    **스크립트**: {script.get('script', 'No transcript available')}
                    
                    """
                
                # 프롬프트에 데이터 삽입
                prompt = prompt_template.replace("{핵심 키워드 데이터}", keywords_data)
                prompt = prompt.replace("{결핍-솔루션 페어 데이터}", "")  # 이미 키워드 데이터에 포함됨
                prompt = prompt.replace("{크롤링한 스크립트 데이터}", scripts_text)
                
                max_retry = 2
                retry_count = 0
                
                while retry_count <= max_retry:
                    try:
                        st.write(f"🔄 배치 {batch_index+1}/{total} Claude API 요청 중...")
                        # 배치별 API 호출
                        response = client.messages.create(
                            model="claude-3-7-sonnet-20250219",
                            max_tokens=8000,
                            temperature=0.4,
                            system="당신은 유튜브 댓글에서 추출한 핵심 키워드와 크롤링한 여러 유튜브 영상 스크립트 사이의 일치점을 찾는 전문가입니다.",
                            messages=[{"role": "user", "content": prompt}]
                        )
                        
                        # 응답 처리
                        st.write(f"✅ 배치 {batch_index+1}/{total} 매칭 분석 완료!")
                        return response.content[0].text
                    except Exception as e:
                        retry_count += 1
                        st.error(f"Claude API 호출 중 오류 발생 (배치 {batch_index+1}): {str(e)}")
                        if retry_count <= max_retry:
                            st.info(f"배치 {batch_index+1} 재시도 중... ({retry_count}/{max_retry})")
                            time.sleep(2)  # 잠시 대기 후 재시도
                        else:
                            st.error(f"최대 재시도 횟수 초과 (배치 {batch_index+1})")
                            return None
                
                return None
            
            # 배치 인덱스에 대해 병렬로 함수 실행
            futures = {executor.submit(process_batch, j): j for j in current_batch_indices}
            
            # 완료된 작업 결과 수집
            for future in concurrent.futures.as_completed(futures):
                batch_index = futures[future]
                completed += 1
                progress = 0.1 + (0.8 * (completed / total))
                update_progress(3, progress)
                
                try:
                    result = future.result()
                    if result:
                        batch_results.append(result)
                except Exception as e:
                    st.error(f"처리 결과 가져오기 실패: {str(e)}")
    
    # 최종 결과 통합
    try:
        update_progress(3, 0.9)  # 진행 상태 90%
        st.write("✅ 모든 배치 처리 완료. 결과 통합 중...")
        
        if len(batch_results) == 0:
            st.error("❌ 모든 배치 처리가 실패했습니다.")
            return None
        
        # 개별 배치 결과에서 추천 영상만 추출
        combined_recommendations = []
        for batch_result in batch_results:
            if batch_result:
                batch_recommendations = extract_batch_recommendations(batch_result)
                combined_recommendations.extend(batch_recommendations)
        
        # 점수 순으로 정렬
        combined_recommendations.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        # 최종 결과 템플릿
        final_result = f"""# 키워드-스크립트 매칭 결과
        
## 최종 추천 영상 (관련성 점수 5.0점 이상)

{format_final_recommendations(combined_recommendations)}

"""
        
        update_progress(3, 1.0)  # 진행 상태 100%
        return final_result
        
    except Exception as e:
        st.error(f"최종 결과 통합 중 오류 발생: {str(e)}")
        st.exception(e)
        return "\n\n".join([result for result in batch_results if result])

# 5. 영업 이메일 생성 함수들
def generate_email_with_claude(recommended_video, keywords_analysis, script_data=None):
    """Claude API를 사용해 맞춤형 영업 이메일 생성"""
    update_progress(4, 0.5)  # 진행 상태 50%
    
    client = get_claude_client()
    
    # 영상 스크립트 찾기
    video_script = None
    if script_data:
        for script in script_data:
            if script['video_id'] == recommended_video.get('video_id'):
                video_script = script.get('script', '')
                break
    
    # 스크립트 내용 요약 (너무 길면 잘라냄)
    script_excerpt = ""
    if video_script:
        if len(video_script) > 3000:
            script_excerpt = video_script[:3000] + "..."
        else:
            script_excerpt = video_script
    
    prompt = f"""
    당신은 온라인 교육 플랫폼 '클래스유'의 사업개발 본부장 강승권입니다. 다음 정보를 바탕으로 선생님에게 보낼 개인화된 영업 이메일을 작성해 주세요.
    
    ## 선생님 정보
    - 채널명: {recommended_video['channel']}
    - 영상 제목: {recommended_video['title']}
    - 영상 URL: {recommended_video['url']}
    
    ## 영상 스크립트 (일부 내용)
    ```
    {script_excerpt}
    ```
    
    ## 키워드 분석 결과
    {keywords_analysis.get('raw_text', '')}
    
    ## 작성 지침
    1. 선생님의 콘텐츠에 대한 진정한 감사와 관심을 표현하세요.
    2. 선생님의 특정 영상(제목 명시)을 봤다고 언급하고, 그 영상에서 어떤 구체적인 부분에 감동받았는지 실제 스크립트 내용을 인용하며 서술하세요.
    3. 결핍-집착 모델에 기반하여 선생님의 콘텐츠가 시청자들의 어떤 심리적 니즈를 충족시키는지 언급하세요.
    4. 클래스유 플랫폼이 어떤 가치를 제공할 수 있는지 구체적으로 설명하세요.
    5. 성공 사례를 간략히 언급하세요 (예: 유근용님 1,138만회, 샤이니쌤 683만회, 월 정산 금액 등).
    6. 구체적인 협업 제안과 다음 단계를 포함하세요.
    7. 친근하고 전문적인 톤을 유지하세요.
    8. 이메일 길이는 300-500단어로 제한하세요.
    
    ## 이메일 형식
    아래 형식을 참고하되, 선생님의 콘텐츠 특성과 스크립트 내용을 반영한 자연스러운 이메일을 작성하세요:
    
    ```
    [선생님 호칭] 안녕하세요~!
    저는 클래스유 사업개발 본부장 강승권이라고 합니다.
    
    **[선생님]의 [특정 콘텐츠/분야]를 더 많은 사람들에게 전달하고 싶어 이렇게 협업을 제안드립니다.**
    
    저는 얼마 전 [선생님]의 "[구체적인 영상 제목]" 영상을 보았습니다. 특히 "[영상에서 인상적이었던 구체적인 내용/말씀 인용]" 부분에 큰 감동을 받았습니다. [이 내용이 나에게 어떤 영향을 주었는지 간략히 설명]
    
    저희는 온라인 클래스 플랫폼으로 **'누구나 자신의 무한한 잠재력을 믿게 만든다'**는 사명을 갖고 수많은 선생님들의 이야기를 회원들에게 전달하는 역할을 하고 있습니다.
    
    [협업 제안 및 다음 단계]
    
    회신 부탁드립니다~!
    ```
    """
    
    try:
        response = client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=2000,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}]
        )
        
        email_content = response.content[0].text
        update_progress(4, 1.0)  # 이 단계 완료
        return email_content
    except Exception as e:
        st.error(f"Claude API 호출 중 오류 발생: {str(e)}")
        return None

# 프롬프트 파일 생성 (계속)
def create_prompt_files():
    # 인사이터 프롬프트 파일
    insighter_prompt = """
# 핵심 키워드 추출 프롬프트

## 시스템 지시사항
당신은 최초 검색 키워드와 댓글 데이터를 분석하여 사용자들이 선생님에게 듣고 싶어하는 말과 표현을 파악하는 전문가입니다. 결핍-집착 모델을 활용하여 댓글에 나타난 심리적 패턴을 객관적으로 분석하고, 선생님이 실제로 사용했을 것으로 추정되는 효과적인 단어와 문구를 추출해야 합니다. 

최초 검색 키워드는 출발점으로 활용하되, 댓글 데이터에서 발견되는 더 넓은 맥락의 결핍과 니즈로 키워드를 확장해야 합니다. 특히 최초 검색어의 직접적 의미를 넘어 그 기저에 있는 심리적, 사회적, 정서적 결핍으로 확장하는 것이 중요합니다.

추출된 키워드는 유튜브에서 좋은 선생님을 검색하는 데 활용될 것입니다. 또한 검색 데이터를 기반으로 각 결핍 유형의 시장성을 평가하여 가장 수요가 높은 콘텐츠 방향을 제시해야 합니다. 최종 결과로는 핵심 키워드와 연관 키워드, 결핍-솔루션 페어, 선생님 발화 추정 문구, 유튜브 검색 최적화 키워드, 검색 데이터 기반 시장성 분석을 제시해주세요.

## 핵심 개념 정의
- **최초 검색 키워드**: 사용자가 처음 입력한 검색어로, 더 깊은 결핍과 니즈로 확장하기 위한 출발점
- **결핍(Deficiency)**: "있어야 할 것이 없는" 상태로, 사용자가 느끼는 부족감
- **집착(Attachment)**: "잡아서 놓지 않는" 상태로, 결핍을 해소하려는 지속적인 욕구
- **주상(住相)**: 특정 대상이나 상태에 "머무르려는 마음"으로, 결핍 해소에 집착하는 심리
- **결핍-솔루션 페어**: 사용자의 결핍과 이를 해결할 수 있는 솔루션의 구체적 매칭
- **키워드 확장**: 최초 검색어의 표면적 의미를 넘어 기저에 있는 다양한 결핍으로 확장하는 과정
- **시장성**: 특정 콘텐츠나 메시지가 시장에서 수요가 높고 사용자들이 적극적으로 반응할 가능성

## 분석 프로세스
1. 최초 검색 키워드의 표면적 의미와 잠재적 의도를 파악하세요.
2. 댓글 데이터를 주의 깊게 읽고 주제와 맥락을 파악하세요.
3. 반복적으로 언급되는 결핍 요소와 집착 패턴을 식별하세요.
4. 식별된 결핍을 최초 검색 키워드와 관련된 것과 그 범위를 넘어선 것으로 구분하세요.
5. 사용자 댓글에서 선생님의 어떤 말이나 표현에 긍정적으로 반응했는지 파악하세요.
6. 그 반응으로부터 선생님이 실제로 사용했을 것으로 추정되는 핵심 단어/문구를 추출하세요.
7. 추출된 단어/문구를 심리적 결핍 유형에 따라 카테고리화하세요.
8. 각 결핍에 대응하는 효과적인 선생님의 언어 패턴을 도출하세요.
9. 댓글의 '좋아요' 수, 공감 반응 등을 고려하여 각 메시지의 잠재적 시장성을 평가하세요.
10. 최초 검색 키워드를 변형 및 확장하여 다양한 결핍 유형을 포괄할 수 있는 유튜브 검색 최적화 키워드를 생성하세요.
11. 결핍-솔루션 페어와 선생님 발화 추정 문구, 유튜브 검색 최적화 키워드, 검색 데이터 기반 시장성 분석을 작성하세요.

## 분석할 최초 검색 키워드:
```
{{INITIAL_SEARCH_KEYWORD}}
```

## 분석할 댓글 데이터:
```
{{COMMENTS_DATA}}
```

## 응답 형식
### 1. 최초 검색어 확장 분석
- **검색 키워드**: [사용자가 입력한 검색어]
- **표면적 의미**: 이 검색어의 일반적인 의미와 직접적 범위
- **잠재적 니즈**: 이 검색어 이면에 있는 실질적 문제와 달성하고자 하는 변화
- **확장 방향**: 이 검색어를 어떤 방향으로 확장할 수 있는지 제시

### 2. 핵심 키워드 및 연관 키워드
- **핵심 결핍 유형 1**: [결핍 유형]
  - **연관 키워드**: 이 결핍과 관련된 구체적인 키워드들
- **핵심 결핍 유형 2**: [결핍 유형]
  - **연관 키워드**: 이 결핍과 관련된 구체적인 키워드들
[계속...]

### 3. 결핍-솔루션 페어
- **결핍**: [구체적인 결핍 요소]
  - **솔루션 키워드**: 이 결핍을 해소할 수 있는 구체적인 솔루션 키워드
[계속...]

### 4. 선생님 발화 추정 문구
- **결핍 유형**: [결핍 유형]
  - **추정 발화 문구 1**: "교육자가 실제로 말했을 법한 구체적이고 영향력 있는 문구"
  - **추정 발화 문구 2**: "교육자가 실제로 말했을 법한 구체적이고 영향력 있는 문구"
[계속...]

### 5. 유튜브 검색 최적화 키워드
1. [검색 최적화 키워드 1]
2. [검색 최적화 키워드 2]
3. [검색 최적화 키워드 3]
...
총 10개의 키워드를 추출합니다. 

### 6. 검색 데이터 기반 시장성 분석
검색 행동 데이터를 기반으로 각 결핍 유형의 시장성을 분석하고 제시해주세요. 최초 검색어 관련 시장과 확장된 결핍 영역의 시장을 모두 다루세요. 예를 들어:
- **결핍 키워드**: [결핍 키워드]
  - **검색 볼륨 분석**: 검색 빈도와 트렌드
  - **결핍-카테고리 매핑**: 이 결핍과 관련된 주요 카테고리와 각 카테고리의 검색 관련성
  - **검색 의도 분석**: 정보 탐색, 구매 의도, 문제 해결 등 검색 목적 분석
  - **콘텐츠 기회 분석**: 미충족 니즈, 경쟁 강도, 콘텐츠 갭
(참고: 시장성 분석은 내부적으로만 진행하고 결과값에는 포함하지 마세요)

## 분석 지침
1. 최초 검색 키워드를 출발점으로 삼되, 댓글에서 발견된 다양한 결핍으로 균형 있게 확장하세요.
2. 최초 검색어의 표면적 의미를 넘어 그 이면에 있는 심리적, 사회적, 정서적 측면을 탐색하세요.
3. 댓글 데이터에서 명시적으로 언급된 결핍과 암묵적으로 드러난 결핍 모두 식별하세요.
4. 단순 빈도가 아닌 심리적 중요도를 기준으로 키워드를 우선순위화하세요.
5. 선생님의 말에 대한 긍정적 반응이 두드러진 댓글에 특히 주목하세요.
6. 사용자가 "이 말이 도움이 되었다", "이런 말을 들었을 때 위로가 됐다" 등의 표현을 한 부분을 중점적으로 분석하세요.
7. 선생님이 실제로 사용했을 법한 문구를 추정할 때, 댓글의 맥락과 반응을 충분히 고려하세요.
8. 유튜브 검색에 최적화된 키워드로 변환할 때는 다음 요소를 고려하세요:
   - 최초 검색어를 직접 활용하거나 변형한 키워드 포함
   - 최초 검색어의 의도를 확장한 키워드 포함
   - 검색 빈도가 높을 것으로 예상되는 표현으로 대체
   - 유튜브에서 일반적으로 사용되는 태그 형식으로 정리
   - 효과적인 키워드 조합 제안
   - 선생님/교육자 관련 수식어 추가
9. 각 핵심 결핍 영역별로 최소 3개의 검색 최적화 키워드/키워드 조합을 제안하세요.
10. 결핍-솔루션 페어는 사용자의 진정한 니즈를 충족시킬 수 있는 방향으로 구성하세요.
11. 시장성 분석은 실제 검색 행동 데이터를 기반으로 하여 객관적인 시장 수요를 평가하세요.
12. 검색 데이터를 분석할 때는 검색 볼륨, 트렌드, 계절성, 연관 검색어, 검색 의도 등을 종합적으로 고려하세요.
13. 결핍-카테고리 매핑을 통해 같은 결핍이라도 어떤 해결책(카테고리)을 사용자들이 선호하는지 파악하세요.
14. 최초 검색어와 직접 관련된 결핍뿐 아니라, 댓글에서 강하게 드러난 다른 결핍 유형도 균형 있게 다루세요.
15. 최종 결과에는 최초 검색어를 직접 활용한 키워드와 확장된 결핍 영역의 키워드가 균형 있게 포함되어야 합니다.
"""
    

# 매칭 프롬프트 파일 (계속)
    matching_prompt = """
당신은 유튜브 댓글에서 추출한 키워드와 영상 스크립트를 분석하여 잠재적 교육 콘텐츠 제작자를 식별합니다.
필터링 기준
다음 콘텐츠는 분석에서 제외하세요:

뉴스/시사 채널 (채널명에 '뉴스', '방송', 'TV' 등 포함)
단순 정보 요약 콘텐츠 (고유한 통찰 없이 사실만 나열)
홍보성 콘텐츠 (특정 제품/서비스 판매가 주목적)

평가 기준 (10점 만점)

콘텐츠 품질 (35%):

실용적이고 구체적인 정보 제공
제작자만의 독특한 관점과 경험


제작자 역량 (35%):

주제에 대한 전문성
명확한 전달력과 시청자와의 연결성


키워드 연관성 (30%):

핵심 키워드와의 연관성
결핍-솔루션 페어와의 관련성



종합 점수 계산
종합 점수 = (콘텐츠 품질×0.35) + (제작자 역량×0.35) + (키워드 연관성×0.3)
입력 데이터
핵심 키워드
{핵심 키워드 데이터}
결핍-솔루션 페어
{결핍-솔루션 페어 데이터}
유튜브 스크립트
{크롤링한 스크립트 데이터}
출력 형식 (5점 이상만 표시)
[영상 ID] - [영상 제목] - 종합 점수: X/10
* 링크: https://www.youtube.com/watch?v=[영상 ID]
* 채널: [채널명]
* 주요 키워드: [키워드1], [키워드2], [키워드3]
* 콘텐츠 품질: X/10 | 제작자 역량: X/10 | 키워드 연관성: X/10

<인사이트>
이 영상은 [주제/소재]에 관한 콘텐츠로, [특징/접근법]이 돋보입니다. 제작자는 [특성/방법론]을 통해 [가치/이점]을 제공합니다. [대상 시청자]에게 유용합니다.
참고사항

모든 점수는 소수점 첫째 자리까지 표시
종합 점수 5점 이상인 영상만 추천
전체 분석 과정 생략하고 최종 결과만 표시
개인의 관점과 전문성이 담긴 교육적 콘텐츠 우선 추천

"""

    # 프롬프트 파일 저장
    with open("insighter_prompt.txt", "w", encoding="utf-8") as f:
        f.write(insighter_prompt)
    
    with open("matching_prompt.txt", "w", encoding="utf-8") as f:
        f.write(matching_prompt)

# 메인 애플리케이션 UI
def main():
    st.title("선생님 발굴 자동화 프로그램")

    # 진행 상태 표시 바
    show_progress_bar()

    # 탭 설정
    tabs = st.tabs(["1. 데이터 수집", "2. 키워드 분석", "3. 스크립트 수집", "4. 콘텐츠 매칭", "5. 영업 이메일 생성"])

    # 1. 데이터 수집 탭
    with tabs[0]:
        st.header("댓글 데이터 수집")

        # 전체 자동화 옵션 선택
        automation_type = st.radio(
            "자동화 방식 선택",
            ["단일 키워드 자동화", "시트에서 키워드 가져오기 (배치 처리)"],
            index=0
        )

        if automation_type == "단일 키워드 자동화":
            # 기존 단일 키워드 자동화 코드
            st.info("단일 키워드 자동화 모드입니다. 아래 설정 후 '자동화 시작' 버튼을 클릭하면 전체 과정이 자동으로 실행됩니다.")

            # 전체 설정 섹션
            st.subheader("전체 프로세스 설정")

            # 1. 데이터 수집 설정
            st.markdown("##### 1. 데이터 수집 설정")
            keyword = st.text_input("키워드 입력 (필수)", key="auto_keyword")
            max_videos = st.slider("수집할 영상 수", 1, 50, 5, key="auto_max_videos")
            max_comments = st.slider("영상당 수집할 댓글 수", 10, 200, 20, key="auto_max_comments")

            # 3. 스크립트 수집 설정
            st.markdown("##### 2. 스크립트 수집 설정")
            max_videos_per_keyword = st.slider("키워드당 수집할 영상 수", 1, 10, 3, key="auto_max_videos_per_keyword")
            filter_duplicate_channels = st.checkbox("중복 채널 필터링", value=True, key="auto_filter_channels")
            min_subscribers = st.number_input("최소 구독자 수", min_value=0, max_value=1000000, value=5000, step=1000, key="auto_min_subscribers", help="이 수치보다 구독자가 적은 채널의 영상은 제외합니다.")

            # 5. 스프레드시트 설정
            st.markdown("##### 3. 스프레드시트 설정")
            spreadsheet_url = st.text_input("결과를 저장할 Google 스프레드시트 URL", value="https://docs.google.com/spreadsheets/d/1t-8cmMXcoR7gU9xGbMpHPPdDnMQjWfnZnA2c_1iQV7I/edit?gid=661484979#gid=661484979", key="auto_spreadsheet_url")

            # 자동화 시작 버튼
            if st.button("🚀 자동화 시작", key="start_single_automation"):
                if not keyword:
                    st.error("❌ 키워드를 입력해주세요.")
                else:
                    with st.spinner("전체 자동화 프로세스를 실행 중입니다..."):
                        try:
                            success = run_full_automation(
                                keyword, 
                                max_videos, 
                                max_comments, 
                                max_videos_per_keyword, 
                                filter_duplicate_channels,
                                min_subscribers,  # 최소 구독자 수 파라미터 추가
                                spreadsheet_url
                            )

                            if success:
                                st.session_state['current_step'] = 5  # 모든 단계 완료 표시
                                st.session_state['progress'] = 100  # 진행률 100%
                        except Exception as e:
                            st.error(f"❌ 자동화 실행 중 오류 발생: {str(e)}")
                            st.exception(e)
        else:
            # 시트에서 키워드 가져와 배치 처리하는 코드
            st.info("배치 처리 모드입니다. 시트에서 키워드를 가져와 자동으로 처리합니다.")

            # 공통 설정 섹션
            st.subheader("배치 프로세스 설정")

            # 스프레드시트 설정
            st.markdown("##### 1. 스프레드시트 설정")
            batch_spreadsheet_url = st.text_input("Google 스프레드시트 URL (키워드 목록 & 결과 저장)", value="https://docs.google.com/spreadsheets/d/1t-8cmMXcoR7gU9xGbMpHPPdDnMQjWfnZnA2c_1iQV7I/edit?gid=661484979#gid=661484979", key="batch_spreadsheet_url")

            # 시트에서 키워드 가져오기 버튼
            if st.button("🔄 시트에서 키워드 가져오기", key="load_keywords"):
                with st.spinner("키워드를 가져오는 중..."):
                    keywords_from_sheet = get_keywords_from_sheet(batch_spreadsheet_url)
                    if keywords_from_sheet:
                        st.session_state['keywords_from_sheet'] = keywords_from_sheet
                    else:
                        st.warning("⚠️ 시트에서 키워드를 가져오지 못했습니다.")

            # 불러온 키워드 표시
            if 'keywords_from_sheet' in st.session_state and st.session_state['keywords_from_sheet']:
                keywords_from_sheet = st.session_state['keywords_from_sheet']
                st.success(f"✅ {len(keywords_from_sheet)}개 키워드를 로드했습니다.")

                with st.expander("불러온 키워드 목록 보기", expanded=False):
                    for i, k in enumerate(keywords_from_sheet):
                        st.write(f"{i+1}. {k}")

                # 실행 설정
                st.markdown("##### 2. 실행 설정")
                execution_count = st.slider("처리할 키워드 수", 1, len(keywords_from_sheet), min(3, len(keywords_from_sheet)))

                # 데이터 수집 설정
                st.markdown("##### 3. 데이터 수집 설정")
                batch_max_videos = st.slider("키워드별 수집할 영상 수", 1, 50, 5, key="batch_max_videos")
                batch_max_comments = st.slider("영상당 수집할 댓글 수", 10, 200, 20, key="batch_max_comments")

                # 스크립트 수집 설정
                st.markdown("##### 4. 스크립트 수집 설정")
                batch_max_videos_per_keyword = st.slider("키워드당 수집할 영상 수", 1, 10, 3, key="batch_max_videos_per_keyword")
                batch_filter_duplicate_channels = st.checkbox("중복 채널 필터링", value=True, key="batch_filter_channels")
                batch_min_subscribers = st.number_input("최소 구독자 수", min_value=0, max_value=1000000, value=5000, step=1000, key="batch_min_subscribers", help="이 수치보다 구독자가 적은 채널의 영상은 제외합니다.")

                # 배치 처리 시작 버튼
                if st.button("🚀 배치 처리 시작", key="start_batch_automation"):
                    with st.spinner(f"{execution_count}개 키워드에 대한 배치 처리를 실행 중입니다..."):
                        try:
                            success = run_batch_automation(
                                batch_spreadsheet_url,
                                keywords_from_sheet,
                                execution_count,
                                batch_max_videos,
                                batch_max_comments,
                                batch_max_videos_per_keyword,
                                batch_filter_duplicate_channels,
                                batch_min_subscribers  # 최소 구독자 수 파라미터 추가
                            )

                            if success:
                                st.balloons()
                                st.success("🎉 모든 배치 처리가 완료되었습니다!")
                        except Exception as e:
                            st.error(f"❌ 배치 처리 중 오류 발생: {str(e)}")
                            st.exception(e)
            else:
                st.info("👆 '시트에서 키워드 가져오기' 버튼을 클릭하여 키워드를 로드해주세요.")
                st.write("""
                **사용 방법**:
                1. 지정한 스프레드시트에 '키워드' 탭을 만들고 키워드를 A열에 입력합니다.
                2. '시트에서 키워드 가져오기' 버튼을 클릭합니다.
                3. 실행 설정에서 처리할 키워드 수를 선택합니다.
                4. '배치 처리 시작' 버튼을 클릭하면 지정한 개수의 키워드가 차례로 처리됩니다.
                5. 처리 결과는 스프레드시트에 자동으로 저장됩니다.
                """)

        # 기존 수동 옵션은 가장 아래로 이동
        st.markdown("---")
        st.subheader("수동 데이터 수집")
        collection_method = st.radio(
            "수집 방법 선택",
            ["키워드 검색", "CSV 파일 업로드", "유튜브 URL 입력"]
        )

        # 이하 기존 수동 수집 코드...

    # 2. 키워드 분석 탭
    with tabs[1]:
        st.header("키워드 분석")

        if st.session_state['comments_data'] is None:
            st.info("먼저 데이터 수집 단계를 완료해주세요.")
        else:
            # 사용자가 입력한 키워드 표시 및 수정 가능하게
            initial_keyword = st.session_state.get('initial_search_keyword', '')
            search_keyword = st.text_input("분석에 사용할 키워드", value=initial_keyword)

            if st.button("키워드 분석 시작") or st.session_state.get('keywords_analysis'):
                if not st.session_state.get('keywords_analysis'):
                    with st.spinner("댓글 데이터를 분석 중입니다..."):
                        # 검색 키워드를 함께 전달하도록 수정된 함수 호출
                        analysis_result = analyze_comments_with_claude(
                            st.session_state['comments_data'], 
                            search_keyword
                        )
                        if analysis_result:
                            structured_analysis = extract_structured_data_from_analysis(analysis_result)
                            st.session_state['keywords_analysis'] = structured_analysis
                            # 사용자가 입력한 검색 키워드 저장
                            st.session_state['initial_search_keyword'] = search_keyword
                            update_progress(2, 0)  # 다음 단계로 진행

                # 분석 결과 표시
                if st.session_state.get('keywords_analysis'):
                    raw_text = st.session_state['keywords_analysis'].get('raw_text', '')
                    st.subheader("분석 결과")
                    st.write(raw_text)

                    # 텍스트 다운로드 버튼
                    st.download_button(
                        label="분석 결과 다운로드",
                        data=raw_text,
                        file_name="keywords_analysis.txt",
                        mime="text/plain"
                    )

    # 3. 스크립트 수집 탭
    with tabs[2]:
        st.header("스크립트 수집")

        if st.session_state.get('keywords_analysis') is None:
            st.info("먼저 키워드 분석 단계를 완료해주세요.")
        else:
            max_videos_per_keyword = st.slider("키워드당 수집할 영상 수", 1, 150, 3)
            filter_duplicate_channels = st.checkbox("중복 채널 필터링", value=True, help="동일한 채널의 여러 영상을 수집하지 않습니다.")
            min_subscribers = st.number_input("최소 구독자 수", min_value=0, max_value=1000000, value=5000, step=1000, help="이 수치보다 구독자가 적은 채널의 영상은 제외합니다.")

            # 스프레드시트 URL 입력 필드 추가
            check_spreadsheet = st.checkbox("스프레드시트에서 이미 수집된 채널 확인", value=True, help="스프레드시트에 이미 저장된 채널의 영상은 수집하지 않습니다.")
            spreadsheet_url = st.text_input("Google 스프레드시트 URL", 
                                          value="https://docs.google.com/spreadsheets/d/1t-8cmMXcoR7gU9xGbMpHPPdDnMQjWfnZnA2c_1iQV7I/edit?gid=1393785591#gid=1393785591",
                                          disabled=not check_spreadsheet)

            # 분석 결과에서 유튜브 검색 최적화 키워드 추출
            if 'keywords_analysis' in st.session_state and st.session_state['keywords_analysis'] is not None:
                keywords_text = st.session_state['keywords_analysis'].get('raw_text', '')
            else:
                keywords_text = ''
            search_keywords = []

            # 유튜브 검색 최적화 키워드 섹션 추출
            if "유튜브 검색 최적화 키워드" in keywords_text:
                search_section = keywords_text.split("유튜브 검색 최적화 키워드")[1]

                # 숫자 다음에 점이 오고 그 뒤에 공백과 키워드가 오는 패턴 찾기
                keyword_pattern = r'\d+\.\s*(.+)'
                matches = re.findall(keyword_pattern, search_section)

                # 추출된 키워드 정리
                search_keywords = []
                for keyword in matches:
                    if keyword and keyword.strip():
                        search_keywords.append(keyword.strip())

                # 최대 10개로 제한
                search_keywords = search_keywords[:10]       

            # 추출된 키워드가 없으면 기본 키워드 제공
            if not search_keywords:
                default_keywords = [
                    "스피치 자신감 키우는 5분 연습법",
                    "논리적 스피치 두괄식 말하기 기법",
                    "스피치 리듬감 3가지 비밀",
                    "말더듬 극복하는 스피치 리듬 훈련",
                    "청중을 사로잡는 스피치 기술"
                ]
                search_keywords = default_keywords
                st.warning("유튜브 검색 최적화 키워드를 찾지 못했습니다. 기본 키워드를 사용합니다.")

            # 추출된 키워드 표시
            st.subheader("유튜브 검색 최적화 키워드")
            for i, keyword in enumerate(search_keywords, 1):
                st.write(f"{i}. {keyword}")

            # 스크립트 수집 버튼 
            script_collect_button = st.button("스크립트 수집 시작")
            if script_collect_button or st.session_state.get('scripts_data'):
                if not st.session_state.get('scripts_data'):
                    try:
                        st.write("✅ 스크립트 수집 버튼 클릭됨")
                        st.write(f"✅ 키워드: {search_keywords}")
                        st.write(f"✅ 키워드당 수집할 영상 수: {max_videos_per_keyword}")
                        st.write(f"✅ 중복 채널 필터링: {'활성화' if filter_duplicate_channels else '비활성화'}")
                        st.write(f"✅ 최소 구독자 수: {min_subscribers}명")

                        with st.spinner("키워드로 스크립트를 수집 중입니다..."):
                            st.write("✅ 스크립트 수집 함수 호출")
                            # URL 매개변수 추가
                            use_sheet_url = spreadsheet_url if check_spreadsheet else None
                            scripts_data = collect_scripts_by_keywords(
                                search_keywords, 
                                max_videos_per_keyword,
                                filter_duplicate_channels,
                                min_duration_seconds=180,
                                max_duration_seconds=1800,
                                max_age_days=1000,
                                min_subscribers=min_subscribers,  # 최소 구독자 수 파라미터 추가
                                spreadsheet_url=use_sheet_url
                            )
                            st.write(f"✅ 수집 결과: {len(scripts_data)}개 스크립트")

                            if scripts_data:
                                st.session_state['scripts_data'] = scripts_data

                                # 채널별 수집 통계
                                channel_counts = {}
                                for script in scripts_data:
                                    channel = script['channel_name']
                                    channel_counts[channel] = channel_counts.get(channel, 0) + 1

                                unique_channels = len(channel_counts)
                                duplicate_channels = sum(1 for count in channel_counts.values() if count > 1)

                                st.success(f"{len(scripts_data)}개 영상의 스크립트가 수집되었습니다. (고유 채널 수: {unique_channels}개, 중복 채널 수: {duplicate_channels}개)")
                                update_progress(3, 0)  # 다음 단계로 진행
                            else:
                                st.error("❌ 스크립트 수집 실패: 수집된 스크립트가 없습니다.")
                    except Exception as e:
                        st.error(f"❌ 스크립트 수집 중 오류 발생: {str(e)}")
                        st.exception(e)  # 상세 오류 출력

                # 수집된 스크립트 표시
                if st.session_state.get('scripts_data'):
                    scripts_data = st.session_state['scripts_data']
                    st.success(f"✅ {len(scripts_data)}개 스크립트 수집 완료")
                    with st.expander("📋 수집된 스크립트 보기", expanded=False):
                        # 채널별 그룹화 표시
                        channel_groups = {}
                        for script in scripts_data:
                            channel = script['channel_name']
                            if channel not in channel_groups:
                                channel_groups[channel] = []
                            channel_groups[channel].append(script)

                        # 채널별 통계 표시
                        st.subheader("채널별 수집 현황")
                        for channel, scripts in channel_groups.items():
                            st.write(f"**{channel}**: {len(scripts)}개 영상")

                        # 스크립트 간략 정보 표시
                        st.subheader("수집된 스크립트 목록")
                        # 중첩된 expander 대신에 간단한 목록으로 표시
                        for i, script in enumerate(scripts_data):
                            st.markdown(f"**{i+1}. {script['title']} - {script['channel_name']}**")
                            st.write(f"조회수: {script.get('view_count', 'N/A')}")
                            st.write(f"구독자 수: {script.get('subscriber_count', 'N/A')}명")  # 구독자 수 표시 추가
                            st.write(f"링크: {script['video_link']}")
                            st.write("스크립트 미리보기:")
                            preview = script.get('script', '')[:500] + '...' if len(script.get('script', '')) > 500 else script.get('script', '')
                            st.text(preview)
                            st.markdown("---")

                    # CSV 다운로드 버튼
                    scripts_df = pd.DataFrame([
                        {
                            'video_id': s['video_id'],
                            'title': s['title'],
                            'channel_name': s['channel_name'],
                            'subscriber_count': s.get('subscriber_count', 0),  # 구독자 수 추가
                            'view_count': s.get('view_count', ''),
                            'video_link': s['video_link'],
                            'script': s.get('script', '')[:1000] + '...' if s.get('script') and len(s.get('script', '')) > 1000 else s.get('script', '')
                        }
                        for s in st.session_state['scripts_data']
                    ])

                    csv = scripts_df.to_csv(index=False)
                    st.download_button(
                        label="스크립트 데이터 CSV 다운로드",
                        data=csv,
                        file_name="scripts_data.csv",
                        mime="text/csv"
                    )

    # 4. 콘텐츠 매칭 탭
    with tabs[3]:
        st.header("콘텐츠 매칭")

        if st.session_state.get('scripts_data') is None:
            st.info("먼저 스크립트 수집 단계를 완료해주세요.")
        else:
            if st.button("콘텐츠 매칭 시작") or st.session_state.get('matching_results'):
                if not st.session_state.get('matching_results'):
                    try:
                        st.write("✅ 콘텐츠 매칭 시작")
                        st.write(f"✅ 키워드 분석 데이터: {len(st.session_state['keywords_analysis'].get('raw_text', ''))} 글자")
                        st.write(f"✅ 스크립트 데이터: {len(st.session_state['scripts_data'])}개 영상")

                        with st.spinner("키워드와 콘텐츠를 매칭 중입니다..."):
                            matching_result = match_content_with_claude(
                                st.session_state['keywords_analysis'],
                                st.session_state['scripts_data']
                            )
                            if matching_result:
                                st.write(f"✅ 매칭 결과: {len(matching_result)} 글자")
                                st.session_state['matching_results'] = matching_result
                                st.write("✅ 추천 영상 추출 중...")

                                # 추천 영상 추출
                                st.session_state['recommended_videos'] = extract_recommended_videos(matching_result)

                                recommended_count = len([v for v in st.session_state['recommended_videos'] if v["score"] >= 5.0])
                                st.write(f"✅ 전체 영상: {len(st.session_state['recommended_videos'])}개, 추천 영상(5.0점 이상): {recommended_count}개")

                                update_progress(4, 0)  # 다음 단계로 진행
                    except Exception as e:
                        st.error(f"❌ 콘텐츠 매칭 중 오류 발생: {str(e)}")
                        st.exception(e)  # 상세 오류 출력

                # 매칭 결과 표시
                if st.session_state.get('matching_results'):
                    # 전체 매칭 결과 표시 (expander로 접어두기)
                    with st.expander("전체 매칭 분석 결과", expanded=False):
                        st.write(st.session_state['matching_results'])

                    # 추천 선생님 목록 표시 - 8.5점 이상인 영상만 표시
                    st.subheader("⭐ 추천 선생님 목록 ⭐")

                    # 8.5점 이상인 영상 필터링
                    recommended_videos = [v for v in st.session_state['recommended_videos'] if v['score'] >= 5.0]

                    if recommended_videos:
                        st.success(f"총 {len(recommended_videos)}명의 추천 선생님을 찾았습니다.")

                        for i, video in enumerate(recommended_videos, 1):
                            # 각 영상을 구분선으로 구분
                            if i > 1:
                                st.markdown("---")

                            col1, col2 = st.columns([1, 3])

                            with col1:
                                # 유튜브 섬네일 표시 (video_id가 있는 경우에만)
                                if video.get('video_id'):
                                    thumbnail_url = f"https://img.youtube.com/vi/{video['video_id']}/mqdefault.jpg"
                                    st.image(thumbnail_url, caption=f"#{i}")
                                else:
                                    # 섬네일이 없는 경우 대체 이미지 또는 텍스트
                                    st.info(f"#{i} 섬네일 없음")

                            with col2:
                                st.markdown(f"### **{video['title']}**")
                                st.markdown(f"**채널**: {video['channel']}")
                                st.markdown(f"**관련성 점수**: **{video['score']}/10**")

                                # URL이 있는 경우에만 표시
                                if video.get('url'):
                                    st.markdown(f"**링크**: [{video['url']}]({video['url']})")
                                else:
                                    st.warning("영상 URL을 찾을 수 없습니다.")

                                # 이메일 생성 버튼
                                email_btn = st.button(f"영업 이메일 생성", key=f"email_btn_{i}")
                                if email_btn:
                                    st.write(f"✅ 이메일 생성 버튼 클릭: {video['title']}")
                                    st.session_state['selected_video'] = video
                                    # 다음 탭으로 이동 안내
                                    st.info("영업 이메일 생성 탭으로 이동하세요.")
                                    update_progress(4, 1.0)  # 이 단계 완료
                    else:
                        st.warning("5.0점 이상인 추천 선생님이 없습니다. 매칭 결과를 확인해주세요.")

                        # 원인 파악을 위한 디버그 정보
                        all_scores = [v.get('score', 0) for v in st.session_state['recommended_videos']]
                        if all_scores:
                            st.info(f"발견된 모든 영상의 점수: {all_scores}")
                        else:
                            st.error("영상 정보를 추출하지 못했습니다.")

                    # 모든 영상 목록 (선택적 표시)
                    with st.expander("모든 분석 영상 목록", expanded=False):
                        st.subheader("분석된 모든 영상")
                        for video in st.session_state['recommended_videos']:
                            video_url = video.get('url', '링크 없음')
                            st.write(f"**{video['title']}** - {video['channel']} (점수: {video['score']}/10) [{video_url}]")

                    # 매칭 결과 다운로드 버튼
                    st.download_button(
                        label="매칭 결과 다운로드",
                        data=st.session_state['matching_results'],
                        file_name="content_matching.txt",
                        mime="text/plain"
                    )

    # 5. 영업 이메일 생성 탭
    with tabs[4]:
        st.header("영업 이메일 생성")

        if st.session_state.get('recommended_videos') is None or st.session_state.get('scripts_data') is None:
            st.info("먼저 콘텐츠 매칭 단계를 완료해주세요.")
        else:
            # 8.5점 이상인 영상 필터링
            recommended_videos = [v for v in st.session_state['recommended_videos'] if v['score'] >= 5.0]

            if not recommended_videos:
                st.warning("5.0점 이상인 추천 선생님이 없습니다. 먼저 매칭 결과를 확인해주세요.")
            else:
                st.success(f"총 {len(recommended_videos)}명의 추천 선생님이 있습니다.")

                # Google 스프레드시트 URL 입력 필드 추가
                spreadsheet_url = st.text_input(
                    "결과를 저장할 Google 스프레드시트 URL",
                    placeholder="https://docs.google.com/spreadsheets/d/1t-8cmMXcoR7gU9xGbMpHPPdDnMQjWfnZnA2c_1iQV7I/edit?gid=1349436437#gid=1349436437"
                )

                # 이메일 생성 및 스프레드시트 저장 버튼
                col1, col2 = st.columns(2)
                with col1:
                    email_generate_btn = st.button("모든 선생님의 영업 이메일 생성")

                all_emails_generated = 'all_emails' in st.session_state

                with col2:
                    sheet_save_btn = st.button(
                        "스프레드시트에 결과 저장",
                        disabled=not (spreadsheet_url and (all_emails_generated or 'all_emails' in st.session_state))
                    )

                # 이메일 생성 처리
                if email_generate_btn or 'all_emails' in st.session_state:
                    if 'all_emails' not in st.session_state:
                        all_emails = {}

                        with st.spinner(f"총 {len(recommended_videos)}명의 선생님을 위한 이메일을 생성 중입니다..."):
                            for i, video in enumerate(recommended_videos):
                                progress_text = f"({i+1}/{len(recommended_videos)}) {video['title']} 처리 중..."
                                st.write(progress_text)

                                try:
                                    email_content = generate_email_with_claude(
                                        video,
                                        st.session_state['keywords_analysis'],
                                        st.session_state['scripts_data']
                                    )
                                    if email_content:
                                        all_emails[video['video_id']] = {
                                            'title': video['title'],
                                            'channel': video['channel'],
                                            'score': video['score'],
                                            'email': email_content
                                        }
                                except Exception as e:
                                    st.error(f"'{video['title']}' 이메일 생성 중 오류 발생: {str(e)}")

                        st.session_state['all_emails'] = all_emails
                        update_progress(4, 1.0)  # 프로세스 완료

                    # 모든 이메일 표시
                    all_emails = st.session_state['all_emails']

                    if all_emails:
                        # 전체 이메일 다운로드 버튼
                        all_emails_text = ""
                        for video_id, data in all_emails.items():
                            all_emails_text += f"\n\n{'='*80}\n"
                            all_emails_text += f"## {data['channel']} - {data['title']} (점수: {data['score']}/10)\n\n"
                            all_emails_text += data['email']
                            all_emails_text += f"\n{'='*80}\n"

                        st.download_button(
                            label="모든 이메일 내용 다운로드",
                            data=all_emails_text,
                            file_name="all_sales_emails.txt",
                            mime="text/plain"
                        )

                        # 각 선생님별 이메일 표시
                        for video_id, data in all_emails.items():
                            with st.expander(f"{data['channel']} - {data['title']} (점수: {data['score']}/10)"):
                                st.write(data['email'])

                                # 개별 이메일 다운로드 버튼
                                st.download_button(
                                    label="이 이메일 다운로드",
                                    data=data['email'],
                                    file_name=f"email_{video_id}.txt",
                                    key=f"dl_{video_id}",
                                    mime="text/plain"
                                )
                    else:
                        st.warning("생성된 이메일이 없습니다.")

                # 스프레드시트 저장 처리# 스프레드시트 저장 처리
                if sheet_save_btn and spreadsheet_url:
                    with st.spinner("스프레드시트에 결과를 저장 중입니다..."):
                        all_emails = st.session_state.get('all_emails', {})
                        matching_results = st.session_state.get('matching_results', '')
                        success, message = save_matching_results_to_sheet(
                            spreadsheet_url,
                            matching_results,
                            st.session_state['recommended_videos'],
                            all_emails
                        )

                        if success:
                            st.success(message)
                        else:
                            st.error(message)
                            
                # 기존 선택 방식도 유지 (선택사항)
                with st.expander("개별 선생님 선택하여 이메일 생성 (선택사항)", expanded=False):
                    video_options = [f"{v['title']} - {v['channel']} (점수: {v['score']})" for v in recommended_videos]
                    selected_option = st.selectbox(
                        "이메일을 생성할 선생님 선택",
                        options=video_options
                    )

                    selected_index = video_options.index(selected_option)
                    selected_video = recommended_videos[selected_index]

                    email_generate_btn = st.button("선택한 선생님의 이메일 생성")
                    if email_generate_btn or st.session_state.get('email_content'):
                        if not st.session_state.get('email_content'):
                            try:
                                st.write(f"✅ 영업 이메일 생성 시작: {selected_video['title']}")
                                st.write(f"✅ 선택된 영상 점수: {selected_video['score']}/10")

                                with st.spinner("맞춤형 영업 이메일을 생성 중입니다..."):
                                    email_content = generate_email_with_claude(
                                        selected_video,
                                        st.session_state['keywords_analysis']
                                    )
                                    if email_content:
                                        st.write(f"✅ 이메일 생성 완료: {len(email_content)} 글자")
                                        st.session_state['email_content'] = email_content
                            except Exception as e:
                                st.error(f"❌ 이메일 생성 중 오류 발생: {str(e)}")
                                st.exception(e)

                        # 이메일 결과 표시
                        if st.session_state.get('email_content'):
                            st.subheader("생성된 개별 이메일")
                            st.write(st.session_state['email_content'])

                            # 이메일 다운로드 버튼
                            st.download_button(
                                label="이메일 다운로드",
                                data=st.session_state['email_content'],
                                file_name="selected_sales_email.txt",
                                mime="text/plain"
                            )

                            # 각 선생님별 이메일 표시
                            for video_id, data in all_emails.items():
                                with st.expander(f"{data['channel']} - {data['title']} (점수: {data['score']}/10)"):
                                    st.write(data['email'])

                                    # 개별 이메일 다운로드 버튼
                                    st.download_button(
                                        label="이 이메일 다운로드",
                                        data=data['email'],
                                        file_name=f"email_{video_id}.txt",
                                        key=f"dl_{video_id}",
                                        mime="text/plain"
                                    )
                        else:
                            st.warning("생성된 이메일이 없습니다.")

                    # 스프레드시트 저장 처리
                    if sheet_save_btn and spreadsheet_url:
                        with st.spinner("스프레드시트에 결과를 저장 중입니다..."):
                            all_emails = st.session_state.get('all_emails', {})
                            success, message = save_matching_results_to_sheet(
                                spreadsheet_url,
                                st.session_state['recommended_videos'],
                                all_emails
                            )

                            if success:
                                st.success(message)
                            else:
                                st.error(message)
# 앱 실행 시 프롬프트 파일 생성
if __name__ == "__main__":
    create_prompt_files()
    main()
