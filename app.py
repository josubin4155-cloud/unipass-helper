import os
os.system("playwright install chromium")
import streamlit as st
import pandas as pd
from playwright.sync_api import sync_playwright
import re

# --- 비밀번호 확인 기능 시작 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.title("🔒 팀 전용 B/L 조회 시스템")
        pwd = st.text_input("접속 비밀번호를 입력하세요", type="password")
        if st.button("확인"):
            if pwd == st.secrets["APP_PASSWORD"]:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("비밀번호가 틀렸습니다.")
        st.stop()

check_password()
# --- 비밀번호 확인 기능 끝 ---

st.set_page_config(page_title="포워딩 B/L & 양하조회 도우미", page_icon="🚢", layout="wide")

def load_contacts():
    if os.path.exists("contacts.csv"):
        try:
            df = pd.read_csv("contacts.csv", encoding="utf-8-sig")
        except:
            df = pd.read_csv("contacts.csv", encoding="cp949")
        
        # 업체명이 같은 중복 데이터가 있으면 하나만 남기고 제거
        if "업체명" in df.columns:
            df = df.drop_duplicates(subset=["업체명"]).reset_index(drop=True)
            
        return df
    return pd.DataFrame(columns=["키워드", "구분", "업체명", "홈페이지", "전화번호"])

def search_unipass(bl_no, bl_type):
    result = {
        "success": False,
        "error": "",
        "carrier": "확인 불가",
        "agency": "확인 불가",
        "terminal": "확인 불가",
        "containers": [],
        "screenshot_path": "unipass_screenshot.png",
        "raw_text": ""
    }
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--disable-gpu', '--no-sandbox', '--disable-dev-shm-usage', '--disable-extensions']
            )
            page = browser.new_page()
            
            # 1. 유니패스 메인 페이지로 이동
            page.goto("https://unipass.customs.go.kr/csp/index.do", timeout=30000, wait_until="domcontentloaded")
            
            # 2. 화물진행정보 영역의 'M B/L - H B/L' 라디오버튼 클릭
            try:
                page.click("label:has-text('M B/L - H B/L')", timeout=3000)
            except:
                try:
                    page.locator("input[value='MH']").click(force=True, timeout=3000)
                except:
                    pass
            
            page.wait_for_timeout(5000) # 라디오 선택 후 입력창 활성화 대기

            # 3. 화물진행정보 박스 내부의 텍스트 입력창들만 정확히 타겟팅
            # 유니패스 메인 우측 상단 화물진행정보 영역 안의 입력창들을 찾습니다.
            try:
                # 화물진행정보 영역 내부의 텍스트 입력 필드들 가져오기
                cargo_inputs = page.locator(".货物进度信息 input[type='text'], table input[type='text'], div input[type='text']")
                # 보통 메인 화면 우측 화물진행정보 탭 안의 입력창들이 순서대로 M B/L, H B/L입니다.
                all_text_inputs = page.locator("input[type='text']").all()
                
                # 상단 검색바를 제외하고 화물진행정보 영역의 입력창 찾기 (보통 페이지 내 중간에 위치)
                target_input = None
                for inp in all_text_inputs:
                    placeholder = inp.get_attribute("placeholder") or ""
                    # 메인 검색바가 아닌 화물진행정보용 입력창 필터링
                    if "화물관리번호" not in placeholder and inp.is_visible():
                        # 위치나 순서상 화물진행정보 입력창일 확률이 높음
                        target_input = inp
                        break
                
                # 안전하게 M B/L / H B/L 입력 필드 직접 선택 셀렉터 사용
                # 유니패스 화면 구조상 M/B는 첫 번째 입력칸, H/B는 두 번째 입력칸
                visible_inputs = []
                for inp in all_text_inputs:
                    if inp.is_visible() and inp.bounding_box() and inp.bounding_box()['y'] > 100: # 상단 네비게이션 제외
                        visible_inputs.append(inp)
                
                if bl_type == "M B/L":
                    # M B/L 입력 (보통 첫 번째 또는 지정된 칸)
                    page.locator("input[name*='mblNo'], input[id*='mblNo']").first.fill(bl_no)
                else:
                    # H B/L 입력
                    page.locator("input[name*='hblNo'], input[id*='hblNo']").first.fill(bl_no)
                    
            except Exception as input_err:
                # 대체 방법: 플레이스홀더나 위치 기반으로 강제 입력
                if bl_type == "M B/L":
                    page.fill("input[name='mblNo']", bl_no)
                else:
                    page.fill("input[name='hblNo']", bl_no)
            
            # 4. 화물진행정보 영역 내의 '조회' 버튼 클릭
            try:
                # 화물진행정보 박스 안에 있는 조회 버튼 정밀 타겟팅
                page.click("tr:has-text('M B/L') button, tr:has-text('B/L') button, #txtBlBtn, text='조회'", timeout=3000)
            except:
                page.keyboard.press("Enter")
            
# 5. 검색 결과 페이지 로딩 대기
            page.wait_for_load_state("domcontentloaded", timeout=15000)
            page.wait_for_timeout(2000) # 결과 테이블 렌더링 대기
            
            # 6. [핵심] M B/L인 경우 결과 목록에서 화물관리번호 링크 클릭하여 상세 페이지 진입
            if bl_type == "M B/L":
                try:
                    # 결과 테이블의 링크가 나타날 때까지 안전하게 대기 후 첫 번째 링크 클릭
                    page.wait_for_selector("table tr td a", timeout=7000)
                    page.locator("table tr td a").first.click()
                    
                    # 상세 페이지로 넘어갈 때까지 대기
                    page.wait_for_load_state("domcontentloaded", timeout=15000)
                    page.wait_for_timeout(3000) # 상세 페이지 정보 렌더링 대기
                except Exception as link_err:
                    print(f"화물관리번호 링크 클릭 중 예외 발생: {link_err}")
            
            # 7. 최종 상세 페이지 화면 캡처 및 텍스트 추출
            page.screenshot(path=result["screenshot_path"], full_page=True)
            body_text = page.inner_text("body")
            result["raw_text"] = body_text

            if "조회된 내역이 없습니다" in body_text or "존재하지 않습니다" in body_text:
                result["error"] = "유니패스에서 해당 B/L 번호의 화물 진행 정보를 찾을 수 없습니다."
                browser.close()
                return result

            # 8. 상세 테이블 정보 파싱
            rows = page.locator("table tr").all()
            for row in rows:
                cells = [c.inner_text().strip() for c in row.locator("th, td").all()]
                for i, cell in enumerate(cells):
                    if "선사/항공사" in cell and i + 1 < len(cells):
                        result["carrier"] = cells[i + 1]
                    elif "선박대리점" in cell and i + 1 < len(cells):
                        result["agency"] = cells[i + 1]
                    elif "터미널" in cell and i + 1 < len(cells):
                        result["terminal"] = cells[i + 1]
            
            found_containers = re.findall(r'[A-Z]{4}\d{7}', body_text)
            result["containers"] = list(set(found_containers))
                        
            browser.close()
            result["success"] = True
            
    except Exception as e:
        result["error"] = f"조회 중 오류가 발생했습니다: {e}"
        
    return result

# 메인 UI 화면 구성
st.title("🚢 포워딩 B/L & 양하조회 자동화 대시보드")
st.markdown("B/L 번호를 입력하면 유니패스를 자동 조회하여 선사/대리점/터미널 연락처와 컨테이너 번호를 보여줍니다.")

with st.sidebar:
    st.header("📋 등록된 선사/터미널 DB")
    contacts_df = load_contacts()
    st.dataframe(contacts_df[["구분", "업체명", "전화번호"]], hide_index=True)
    st.info("💡 `contacts.csv` 파일을 수정하면 선사 정보를 언제든 추가할 수 있습니다.")

col_type, col_input, col_btn = st.columns([1.2, 3, 1])
with col_type:
    bl_type = st.selectbox("B/L 구분", ["H B/L", "M B/L"])
with col_input:
    bl_no = st.text_input("B/L 번호 입력", placeholder="예: HDMU1234567").strip().upper()
with col_btn:
    st.write("")
    st.write("")
    search_clicked = st.button("🔍 유니패스 조회", type="primary", use_container_width=True)

st.divider()

if search_clicked:
    if not bl_no:
        st.warning("B/L 번호를 입력해 주세요!")
    else:
        with st.spinner(f"유니패스에서 [{bl_no}] 화물 정보를 조회 중입니다..."):
            data = search_unipass(bl_no, bl_type)
            
        if not data["success"]:
            st.error(data["error"])
            if os.path.exists(data["screenshot_path"]):
                st.image(data["screenshot_path"], caption="유니패스 조회 화면 캡처")
        else:
            st.success(f"✅ [{bl_no}] 조회가 완료되었습니다!")
            
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("선사 / 항공사", data["carrier"])
            with c2:
                st.metric("선박대리점", data["agency"])
            with c3:
                st.metric("장치장 (터미널)", data["terminal"])
                
            st.markdown("---")
            
            left_col, right_col = st.columns([1.2, 1])
            
            with left_col:
                st.subheader("📞 매칭된 선사 및 터미널 연락처")
                search_target_text = f"{data['carrier']} {data['agency']} {data['terminal']} {data['raw_text']}"
                matched_rows = []
                seen_companies = set()
                
                for _, row in contacts_df.iterrows():
                    keyword = str(row["키워드"]).strip()
                    company = str(row["업체명"]).strip()
                    if keyword and keyword in search_target_text and company not in seen_companies:
                        matched_rows.append(row)
                        seen_companies.add(company)
                
                if matched_rows:
                    for item in matched_rows:
                        with st.container(border=True):
                            st.markdown(f"**[{item['구분']}] {item['업체명']}**")
                            st.write(f"☎️ **전화번호:** `{item['전화번호']}`")
                            if pd.notna(item['홈페이지']) and str(item['홈페이지']).startswith("http"):
                                st.link_button(f"🌐 {item['업체명']} 홈페이지 바로가기", item['홈페이지'])
                else:
                    st.info("등록된 선사/터미널 DB와 일치하는 업체가 없습니다.")

            with right_col:
                st.subheader("📦 컨테이너 번호 (클릭하여 복사)")
                if data["containers"]:
                    for cntr in data["containers"]:
                        st.code(cntr, language=None)
                else:
                    st.warning("표준 컨테이너 번호를 찾지 못했습니다.")
            
            st.markdown("---")
            st.subheader("📸 유니패스 조회 결과 캡처")
            if os.path.exists(data["screenshot_path"]):
                st.image(data["screenshot_path"], use_container_width=True)
