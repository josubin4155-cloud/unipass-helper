import os
os.system("playwright install chromium")
import streamlit as st
import pandas as pd
from playwright.sync_api import sync_playwright
import re
import time
import concurrent.futures

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

st.set_page_config(page_title="FNH LOGISTICS - B/L & 양하조회 대시보드", page_icon="🚢", layout="wide")

# 🎨 [FNH 로지스틱스 브랜드 커스텀 CSS 적용]
st.markdown("""
    <style>
    /* 전체 배경 톤앤매너: 세련된 소프트 오프화이트 */
    .stApp {
        background-color: #f8fafc;
    }
    
    /* 타이틀 및 헤더 스타일 (딥 네이비 감성) */
    h1 {
        font-weight: 800 !important;
        color: #0f172a !important;
        letter-spacing: -0.5px;
    }
    h2, h3 {
        color: #1e293b !important;
        font-weight: 700 !important;
    }
    
    /* 상단 요약 메트릭 카드 디자인 (화이트 카드 + 입체 테두리) */
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        padding: 18px 20px;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
    }
    div[data-testid="stMetric"] label {
        color: #64748b !important;
        font-weight: 600 !important;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        color: #0f172a !important;
    }
    
    /* 🔍 유니패스 조회 버튼 (FNH 로고 포인트 레드 적용) */
    button[kind="primary"] {
        background-color: #e11d48 !important;
        border-color: #e11d48 !important;
        color: #ffffff !important;
        font-weight: 600 !important;
        border-radius: 8px !important;
    }
    button[kind="primary"]:hover {
        background-color: #be123c !important;
        border-color: #be123c !important;
    }
    
    /* 컨테이너 번호 코드 박스 */
    div[data-testid="stCode"] {
        border-radius: 8px !important;
        border: 1px solid #cbd5e1 !important;
        background-color: #ffffff !important;
    }
    
    /* 사이드바 스타일 정돈 */
    section[data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #e2e8f0;
    }
    </style>
""", unsafe_allow_html=True)

def load_contacts():
    if os.path.exists("contacts.csv"):
        try:
            df = pd.read_csv("contacts.csv", encoding="utf-8-sig")
        except:
            df = pd.read_csv("contacts.csv", encoding="cp949")
        
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
        "arrival_date": "확인 불가",
        "terminal": "확인 불가",
        "latest_location": "확인 불가",
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
            
            # PC 와이드 해상도(1920x1080) 지정
            page = browser.new_page(viewport={"width": 1920, "height": 1080})
            
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
            
            page.wait_for_timeout(1000)

            # 3. M B/L 또는 H B/L 입력창에 번호 입력
            try:
                if bl_type == "M B/L":
                    page.locator("input[name*='mblNo'], input[id*='mblNo']").first.fill(bl_no)
                else:
                    page.locator("input[name*='hblNo'], input[id*='hblNo']").first.fill(bl_no)
            except Exception as input_err:
                if bl_type == "M B/L":
                    page.fill("input[name='mblNo']", bl_no)
                else:
                    page.fill("input[name='hblNo']", bl_no)
            
            # 4. 조회 버튼 클릭
            try:
                page.click("tr:has-text('M B/L') button, tr:has-text('B/L') button, #txtBlBtn, text='조회'", timeout=3000)
            except:
                page.keyboard.press("Enter")
            
            # 5. 검색 결과 페이지 로딩 대기
            page.wait_for_load_state("domcontentloaded", timeout=15000)
            page.wait_for_timeout(2000)
            
            # 6. M B/L인 경우 결과 목록에서 화물관리번호 링크 클릭하여 상세 페이지 진입
            if bl_type == "M B/L":
                try:
                    page.wait_for_selector("table tr td a", timeout=7000)
                    page.locator("table tr td a").first.click()
                    page.wait_for_load_state("domcontentloaded", timeout=15000)
                    page.wait_for_timeout(2000)  # 데이터 렌더링 안정 대기
                except Exception as link_err:
                    print(f"화물관리번호 링크 클릭 중 예외 발생: {link_err}")
            
            # 7. 데이터가 완벽히 채워진 후 고화질 현재 화면 캡처 및 텍스트 추출
            page.screenshot(path=result["screenshot_path"])
            body_text = page.inner_text("body")
            result["raw_text"] = body_text

            if "조회된 내역이 없습니다" in body_text or "존재하지 않습니다" in body_text:
                result["error"] = "유니패스에서 해당 B/L 번호의 화물 진행 정보를 찾을 수 없습니다."
                browser.close()
                return result

            # 8. 상세 테이블 정보 파싱 (선사, 대리점, 입항일, 터미널 추출)
            rows = page.locator("table tr").all()
            for row in rows:
                cells = [c.inner_text().strip() for c in row.locator("th, td").all()]
                for i, cell in enumerate(cells):
                    if "선사/항공사" in cell and i + 1 < len(cells):
                        if "확인 불가" in result["carrier"] or not result["carrier"]:
                            result["carrier"] = cells[i + 1]
                    elif "선박대리점" in cell and i + 1 < len(cells):
                        if "확인 불가" in result["agency"] or not result["agency"]:
                            result["agency"] = cells[i + 1]
                    elif "입항일" in cell and i + 1 < len(cells):
                        val = cells[i + 1]
                        if val and len(val) < 25:
                            result["arrival_date"] = val
                    elif ("터미널" in cell or "장치장" in cell) and i + 1 < len(cells):
                        val = cells[i + 1]
                        if val and "KG" not in val and "톤" not in val and len(val) < 30:
                            result["terminal"] = val

            # 9. 실시간 장치장명(가장 최근 정보: 링크 바로 아래 텍스트) 추출 파싱[cite: 9, 10]
            try:
                headers = [th.inner_text().strip() for th in page.locator("table th").all()]
                target_col_idx = -1
                for idx, h in enumerate(headers):
                    if "장치장" in h:
                        target_col_idx = idx
                        break
                
                if target_col_idx != -1:
                    table_rows = page.locator("table tr").all()
                    for row in table_rows:
                        tds = row.locator("td").all()
                        if len(tds) > target_col_idx:
                            cell_text = tds[target_col_idx].inner_text().strip()
                            lines = [l.strip() for l in cell_text.split('\n') if l.strip()]
                            # 첫 줄은 코드(링크), 둘째 줄이 장치장명 (예: (주)스카이국제운송)[cite: 9, 10]
                            if len(lines) >= 2:
                                result["latest_location"] = lines[1]
                                break
                            elif len(lines) == 1 and not lines[0].isdigit():
                                result["latest_location"] = lines[0]
                                break
            except Exception as loc_parse_err:
                print(f"실시간 장치장명 파싱 중 오류: {loc_parse_err}")
            
            found_containers = re.findall(r'[A-Z]{4}\d{7}', body_text)
            result["containers"] = list(set(found_containers))
                        
            browser.close()
            result["success"] = True
            
    except Exception as e:
        result["error"] = f"조회 중 오류가 발생했습니다: {e}"
        
    return result

# 메인 UI 화면 구성
st.title("🚢 FNH LOGISTICS - B/L & 양하조회 대시보드")
st.markdown("B/L 번호를 입력하면 유니패스를 자동 조회하여 선사/대리점/입항일 정보와 연락처, 컨테이너 번호를 보여줍니다.")

with st.sidebar:
    st.header("📋 등록된 선사/터미널 DB")
    
    uploaded_file = st.file_uploader("새로운 contacts.csv 파일 업로드", type=["csv"])
    if uploaded_file is not None:
        with open("contacts.csv", "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.success("DB 파일이 성공적으로 업데이트되었습니다!")
        st.rerun()

    contacts_df = load_contacts()
    st.dataframe(contacts_df[["구분", "업체명", "전화번호"]], hide_index=True)
    st.info("💡 파일을 업로드하면 즉시 DB에 반영됩니다.")

col_type, col_input, col_btn = st.columns([1, 2.5, 1.3])
with col_type:
    bl_type = st.selectbox("B/L 구분", ["M B/L", "H B/L"])
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
        loading_placeholder = st.empty()
        
        loading_steps = [
            ("🚢", f"[{bl_no}] 화물을 향해 출항 준비 중..."),
            ("🌊", "파도를 헤치고 유니패스 서버로 전력 질주 중..."),
            ("⚓", "선사, 대리점, 입항일 정보를 낚아채는 중..."),
            ("📦", "컨테이너 번호와 실시간 장치장명을 말끔히 정리하는 중...")
        ]
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(search_unipass, bl_no, bl_type)
            
            idx = 0
            while not future.done():
                emoji, msg = loading_steps[idx % len(loading_steps)]
                loading_placeholder.markdown(f"⏳ {emoji} {msg}")
                time.sleep(0.5)
                idx += 1
                
            data = future.result()
        
        loading_placeholder.empty()

        if not data["success"]:
            st.error(data["error"])
            if os.path.exists(data["screenshot_path"]):
                st.image(data["screenshot_path"], caption="유니패스 조회 화면 캡처")
        else:
            st.success(f"✅ [{bl_no}] 조회가 완료되었습니다!")
            
            # 상단 3개 카드: 선사/항공사, 선박대리점, 입항일
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("선사 / 항공사", data["carrier"])
            with c2:
                st.metric("선박대리점", data["agency"])
            with c3:
                st.metric("입항일", data["arrival_date"])
                
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
                
                st.markdown("")
                st.subheader("📍 실시간 최신 장치장명")
                st.info(f"🏢 **{data['latest_location']}**")
            
            st.markdown("---")
            st.subheader("📸 유니패스 조회 결과 캡처")
            if os.path.exists(data["screenshot_path"]):
                with open(data["screenshot_path"], "rb") as file:
                    st.download_button(
                        label="📥 선명한 원본 캡처 이미지 다운로드 (.png)",
                        data=file,
                        file_name=f"UNIPASS_{bl_no}.png",
                        mime="image/png",
                        use_container_width=True
                    )
                st.image(data["screenshot_path"], use_container_width=True)
