import io
import re
import time
import random
import requests
import json
import textwrap
import numpy as np
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup
from urllib.parse import quote
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# =============================================
#   デザインとヘッダー設定
# =============================================
st.set_page_config(page_title="Creema市場リサーチツール", page_icon="💎", layout="wide")

st.markdown("""
    <style>
    .block-container { padding-top: 2.5rem !important; padding-bottom: 2rem !important; }
    html, body, [data-testid="stMarkdownContainer"] p, .stMarkdown p {
        font-size: 14px !important;
        font-family: "Meiryo", "Helvetica Neue", Arial, sans-serif;
        line-height: 1.5 !important;
    }
    h1 { font-size: 28px !important; font-weight: 700 !important; color: #111111 !important; margin: 0 !important; }
    div[data-testid="stSidebarUserContent"] { padding-top: 1rem !important; }
    div[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h5 { font-size: 13.5px !important; margin-top: 12px !important; margin-bottom: 5px !important; color: #111111 !important; font-weight: 600 !important; }
    
    .stTextInput input, .stNumberInput input, .stDateInput input, div[data-testid="stSelectbox"] div { 
        padding: 4px 8px !important; 
        min-height: 32px !important; 
        height: 32px !important; 
        font-size: 13px !important; 
    }
    
    div[data-testid="stNumberInput"] button {
        display: none !important;
    }
    div[data-testid="stNumberInput"] div[data-baseline="true"] {
        padding-right: 8px !important;
    }
    
    .metric-card {
        background-color: #f8f9fa;
        border-left: 5px solid #1f497d;
        padding: 15px;
        border-radius: 4px;
        margin-bottom: 15px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("💎 Creema市場リサーチツール")
st.markdown('<hr style="border: none; border-top: 1px solid #e6e6e6; margin-top: 15px; margin-bottom: 25px; padding: 0;">', unsafe_allow_html=True)

# =============================================
#   サイドバー：設定エリア ＆ フィルターエリア
# =============================================
st.sidebar.header("⚙️ 取得条件設定")
mode = st.sidebar.radio("収集モードを選択してください", ("キーワード検索", "一覧URL直貼り"))

search_keyword = ""
target_url = ""

if mode == "キーワード検索":
    search_keyword = st.sidebar.text_input("🔍 検索キーワードを入力", value="")
    encoded_keyword = quote(search_keyword)
    target_url = f"https://www.creema.jp/listing?q={encoded_keyword}&active=pc_listing-form"
else:
    target_url = st.sidebar.text_input("🔗 Creemaの一覧URLを入力", value="")

max_items = st.sidebar.number_input("🔢 取得する商品件数", min_value=1, max_value=500, value=10, step=10)
start_button = st.sidebar.button("🚀 リサーチを開始する", type="primary")

# 🌟 フィルターの初期値を「制限なし（全表示）」に修正
st.sidebar.markdown('---')
st.sidebar.header("📊 表示データの絞り込み")

# 十分に広い日付範囲を定義
past_limit_date = datetime.strptime("2000-01-01", "%Y-%m-%d").date()
future_limit_date = datetime.strptime("2030-12-31", "%Y-%m-%d").date()

# 1. 購入者数
st.sidebar.markdown("**購入者数**")
col_buy1, col_buy_tilde, col_buy2 = st.sidebar.columns([4, 1, 4])
with col_buy1:
    min_buy = st.number_input("購入者数（最小）", min_value=0, value=0, label_visibility="collapsed")
with col_buy_tilde:
    st.markdown("<div style='text-align: center; line-height: 32px;'>〜</div>", unsafe_allow_html=True)
with col_buy2:
    max_buy = st.number_input("購入者数（最大）", min_value=0, value=99999, label_visibility="collapsed")

# 2. 直近販売日１
st.sidebar.markdown("**直近販売日１**")
col_d1_1, col_d1_tilde, col_d1_2 = st.sidebar.columns([4, 1, 4])
with col_d1_1:
    min_date1 = st.date_input("直近販売日1（最小）", value=past_limit_date, label_visibility="collapsed")
with col_d1_tilde:
    st.markdown("<div style='text-align: center; line-height: 32px;'>〜</div>", unsafe_allow_html=True)
with col_d1_2:
    max_date1 = st.date_input("直近販売日1（最大）", value=future_limit_date, label_visibility="collapsed")

# 3. 直近販売日３
st.sidebar.markdown("**直近販売日３**")
col_d3_1, col_d3_tilde, col_d3_2 = st.sidebar.columns([4, 1, 4])
with col_d3_1:
    min_date3 = st.date_input("直近販売日3（最小）", value=past_limit_date, label_visibility="collapsed")
with col_d3_tilde:
    st.markdown("<div style='text-align: center; line-height: 32px;'>〜</div>", unsafe_allow_html=True)
with col_d3_2:
    max_date3 = st.date_input("直近販売日3（最大）", value=future_limit_date, label_visibility="collapsed")

# 4. 総評価数
st.sidebar.markdown("**総評価数**")
col_rev1, col_rev_tilde, col_rev2 = st.sidebar.columns([4, 1, 4])
with col_rev1:
    min_rev = st.number_input("総評価数（最小）", min_value=0, value=0, label_visibility="collapsed")
with col_rev_tilde:
    st.markdown("<div style='text-align: center; line-height: 32px;'>〜</div>", unsafe_allow_html=True)
with col_rev2:
    max_rev = st.number_input("総評価数（最大）", min_value=0, value=99999, label_visibility="collapsed")

# =============================================
#   📲 LINE通知関数
# =============================================
def send_line_notification(keyword_or_url, item_count):
    LINE_ACCESS_TOKEN = "SsJj64qF912H/fusrwNgsiMS6bgJqv5C9i5Rx1HlHAmux8AmFlC7Q9Pnx5pbQD/4LXbi2ftiFf1zalCCDcGQAcXBxfakpnkBPLZkKzn5G2gbuQc2vkcn2GbCJ2Yf1HmfEWQoo8KbqqJn4/tsoPr4TwdB04t89/1O/w1cDnyilFU="
    LINE_USER_ID = "Ub5228833332f8fd37bbd3d9072853f2c"
    url = "https://api.line.me/v2/bot/message/push"
    headers = { "Content-Type": "application/json", "Authorization": f"Bearer {LINE_ACCESS_TOKEN}" }
    message_text = f"💎 【Creemaツール】利用通知\n\nリサーチ開始！\n内容:\n{keyword_or_url}\n上限: {item_count} 件"
    try: requests.post(url, headers=headers, json={"to": LINE_USER_ID, "messages": [{"type": "text", "text": message_text}]}, timeout=5)
    except: pass

# =============================================
#   Excelダウンロード用バイナリ生成関数
# =============================================
def convert_df_to_excel(df):
    export_df = df.copy()
    def remove_illegal_chars(val):
        if isinstance(val, str):
            cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", val)
            return "".join(ch for ch in cleaned if ch.isprintable() or ch in "\n\r\t")
        return val

    for col in export_df.columns:
        export_df[col] = export_df[col].apply(remove_illegal_chars)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        export_df.to_excel(writer, sheet_name="リサーチ結果", index=False)
        worksheet = writer.sheets["リサーチ結果"]
        
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        header_font = Font(name="Meiryo", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
        data_font = Font(name="Meiryo", size=10)
        thin_border = Border(left=Side(style='thin', color='D9D9D9'), right=Side(style='thin', color='D9D9D9'), top=Side(style='thin', color='D9D9D9'), bottom=Side(style='thin', color='D9D9D9'))
        
        for row in worksheet.iter_rows(min_row=1, max_row=len(export_df)+1):
            for cell in row:
                cell.border = thin_border
                if cell.row == 1:
                    cell.font = header_font
                    cell.fill = header_fill
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                else:
                    cell.font = data_font
                    if cell.column in [1, 4, 6, 7]: 
                        cell.alignment = Alignment(horizontal="right", vertical="center")
                    elif cell.column in [8, 9, 10, 11, 12, 13]: 
                        cell.alignment = Alignment(horizontal="center", vertical="center")
                    else: 
                        cell.alignment = Alignment(horizontal="left", vertical="center")
                        
        for col in worksheet.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            worksheet.column_dimensions[col[0].column_letter].width = min(max(max_len + 3, 10), 50)
            
    return output.getvalue()

# =============================================
#   1件詳細解析用パーツ
# =============================================
def _internal_fetch_item(item_data, headers, one_month_ago):
    link = item_data["link"]
    creator = item_data["creator"]
    title = item_data["title"]
    price = item_data["price"]
    
    favorite = 0
    purchase_count = 0
    review = 0
    recent_review_display = "0件"
    first_review_date = "データなし"
    description_text = "取得失敗"
    recent_sales = ["3ヶ月以上前", "3ヶ月以上前", "3ヶ月以上前"]

    try:
        res = requests.get(link, headers=headers, timeout=10)
        if res.status_code != 200: return None
        soup = BeautifulSoup(res.content, "html.parser")
        
        desc_tag = soup.select_one(".p-item-detail__description, .p-item-detail-body__description")
        if desc_tag:
            description_text = desc_tag.text.strip()
            
        fav_tag = soup.select_one(".p-item-detail-body__action-favorite-count, .c-favorite-btn__count")
        if fav_tag:
            fav_text = re.sub(r"\D", "", fav_tag.text)
            favorite = int(fav_text) if fav_text else 0
            
        rating_link_tag = soup.select_one('a[href*="/rating/sale"]')
        if rating_link_tag:
            review_text = rating_link_tag.text.strip()
            review = int(re.sub(r"\D", "", review_text)) if re.sub(r"\D", "", review_text) else 0
            purchase_count = review
            
            try:
                href_attr = rating_link_tag["href"]
                base_rating_url = href_attr if href_attr.startswith("http") else "https://www.creema.jp" + href_attr
                if "?" in base_rating_url:
                    base_rating_url = base_rating_url.split("?")[0]
                
                all_found_dates = []
                current_page = 1
                clean_target = " ".join(title.strip().split())
                
                while current_page <= 3:
                    current_url = f"{base_rating_url}?page={current_page}"
                    r_res = requests.get(current_url, headers=headers, timeout=10)
                    if r_res.status_code != 200: break
                    r_soup = BeautifulSoup(r_res.content, "html.parser")
                    
                    blocks = r_soup.select(".p-creator-rating-list__item, .p-creator-rating-rating__content")
                    if not blocks: break
                        
                    for block in blocks:
                        title_tags = block.select(".p-creator-rating-rating__title a, .p-creator-rating-list__item-title a")
                        is_target = False
                        for t in title_tags:
                            if " ".join(t.text.strip().split()) == clean_target:
                                is_target = True
                                break
                        
                        if is_target:
                            date_tag = block.select_one(".p-creator-rating-rating__date, .p-creator-rating-list__item-date")
                            if date_tag:
                                date_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", date_tag.text)
                                if date_match:
                                    all_found_dates.append(datetime.strptime(date_match.group(1), "%Y.%m.%d"))
                    current_page += 1
                    time.sleep(0.1)
                
                all_found_dates.sort(reverse=True)
                if all_found_dates:
                    for idx, d_obj in enumerate(all_found_dates[:3]):
                        recent_sales[idx] = d_obj.strftime("%Y.%m.%d")
            except:
                pass

        if rating_link_tag:
            try:
                href_attr = rating_link_tag["href"]
                base_rating_url = href_attr if href_attr.startswith("http") else "https://www.creema.jp" + href_attr
                if "?" in base_rating_url: base_rating_url = base_rating_url.split("?")[0]
                
                rating_res = requests.get(base_rating_url, headers=headers, timeout=10)
                if rating_res.status_code == 200:
                    rating_soup = BeautifulSoup(rating_res.content, "html.parser")
                    
                    voices = rating_soup.select(".p-creator-rating-list__item, .p-creator-rating-rating__content")
                    recent_count = 0
                    for voice in voices:
                        date_tag = voice.select_one(".p-creator-rating-rating__date, .p-creator-rating-list__item-date")
                        if date_tag:
                            date_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", date_tag.text.strip())
                            if date_match and datetime.strptime(date_match.group(1), "%Y.%m.%d") >= one_month_ago:
                                recent_count += 1
                    recent_review_display = f"{recent_count}件"
                    
                    last_page_url = base_rating_url
                    paging_links = rating_soup.select(".c-pagination a")
                    page_nums = []
                    for link_tag in paging_links:
                        p_match = re.search(r"page=(\d+)", link_tag.get("href", ""))
                        if p_match: page_nums.append(int(p_match.group(1)))
                    
                    if page_nums:
                        last_page_url = f"{base_rating_url}?page={max(page_nums)}"
                        
                    last_res = requests.get(last_page_url, headers=headers, timeout=10)
                    if last_res.status_code == 200:
                        last_soup = BeautifulSoup(last_res.content, "html.parser")
                        last_voices = last_soup.select(".p-creator-rating-list__item, .p-creator-rating-rating__content")
                        oldest_dates = []
                        for v in last_voices:
                            d_tag = v.select_one(".p-creator-rating-rating__date, .p-creator-rating-list__item-date")
                            if d_tag:
                                dm = re.search(r"(\d{4}\.\d{2}\.\d{2})", d_tag.text)
                                if dm: oldest_dates.append(datetime.strptime(dm.group(1), "%Y.%m.%d"))
                        if oldest_dates:
                            first_review_date = min(oldest_dates).strftime("%Y.%m.%d")
            except:
                pass

        return {
            "No.": 0, "作家名": creator, "商品名": title, "価格(円)": price, "商品URL": link,
            "お気に入り数": favorite, "購入者数": purchase_count,  
            "直近販売日1": recent_sales[0], "直近販売日2": recent_sales[1], "直近販売日3": recent_sales[2],
            "総評価数": review, "直近1ヶ月の評価数": recent_review_display, "一番初めの評価日": first_review_date,
            "作品紹介文": description_text 
        }
    except:
        return None

# =============================================
#   メインのスクレイピング制御関数
# =============================================
def scrape_creema_fast(start_url, max_num):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
    }
    today = datetime.now()
    one_month_ago = today - timedelta(days=30)
    
    all_item_elements_data = []
    current_url = start_url
    page_count = 1
    detected_market_total = 0 
    page_status = st.empty()
    
    while current_url and len(all_item_elements_data) < max_num:
        page_status.info(f" ページ巡回中... 現在 {page_count} ページ目をスキャンしています (収集済リンク: {len(all_item_elements_data)}件)")
        try:
            response = requests.get(current_url, headers=headers, timeout=10)
            if response.status_code != 200: break
            soup = BeautifulSoup(response.content, "html.parser")
            
            if page_count == 1:
                search_count_element = soup.find(string=re.compile(r"検索結果\s*[\d,]+件"))
                if search_count_element:
                    match_count = re.search(r"検索結果\s*([\d,]+)件", search_count_element)
                    if match_count:
                        detected_market_total = int(match_count.group(1).replace(",", ""))
            
            items = soup.select("article.c-item-article")
            if not items: break
                
            for item in items:
                if len(all_item_elements_data) >= max_num: break
                title_tag = item.select_one('.c-item-article__name a[href*="/item/"]')
                if not title_tag: continue
                    
                title = title_tag.text.strip()
                link = "https://www.creema.jp" + title_tag["href"]
                
                desc_tag = item.select_one(".c-item-article__desc")
                creator, price = "取得失敗", 0
                if desc_tag and "/" in desc_tag.text:
                    parts = desc_tag.text.split("/")
                    price = int(re.sub(r"\D", "", parts[0])) if parts[0] else 0
                    creator = parts[1].strip()
                
                all_item_elements_data.append({"link": link, "creator": creator, "title": title, "price": price})
            
            next_tag = soup.select_one("a.c-pagination__next")
            if next_tag and "href" in next_tag.attrs:
                current_url = next_tag["href"] if next_tag["href"].startswith("http") else "https://www.creema.jp" + next_tag["href"]
                page_count += 1
                time.sleep(0.3)
            else:
                current_url = None
        except:
            break
            
    page_status.empty()
    total_found = len(all_item_elements_data)
    if total_found == 0: return None
        
    status_text = st.empty()
    progress_bar = st.progress(0)
    scraped_data = []
    
    max_workers = 4 if total_found > 100 else 8
    current_idx = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_item = {
            executor.submit(_internal_fetch_item, item_data, headers, one_month_ago): item_data 
            for item_data in all_item_elements_data
        }
        for future in as_completed(future_to_item):
            result = future.result()
            current_idx += 1
            if result: scraped_data.append(result)
            progress_bar.progress(min(current_idx / total_found, 1.0))
            status_text.text(f"⏳ 大規模解析中... 完了: {current_idx} / {total_found} 件")
                
    progress_bar.empty()
    status_text.empty()
    
    if scraped_data:
        for i, item in enumerate(scraped_data, 1): item["No."] = i
        return {"items": scraped_data, "market_total": detected_market_total}
    return None

# =============================================
#    ⚙️ アプリ実行処理エリア
# =============================================
if "raw_data" not in st.session_state: st.session_state.raw_data = None
if "market_total" not in st.session_state: st.session_state.market_total = 0

if start_button:
    if (mode == "一覧URL直貼り" and not target_url) or (mode == "キーワード検索" and not search_keyword):
        st.error("⚠️ 条件を入力してください。")
    else:
        cond_text = f"キーワード: {search_keyword}" if mode == "キーワード検索" else f"直貼りURL: {target_url}"
        send_line_notification(cond_text, max_items)
        
        with st.spinner("🔄 Creemaのデータを徹底解析中..."):
            res_dict = scrape_creema_fast(target_url, max_items)
            
        if res_dict:
            st.session_state.raw_data = res_dict["items"]
            st.session_state.market_total = res_dict["market_total"]
            st.success(f"🎉 リサーチ完了！ 全 {len(res_dict['items'])} 件のデータを取得しました。")
        else:
            st.error("❌ データが取得できませんでした。")

# --- 画面表示処理 ---
if st.session_state.raw_data is not None:
    raw_df = pd.DataFrame(st.session_state.raw_data)
    
    # 数値変換の安全処理
    raw_df["購入者数"] = pd.to_numeric(raw_df["購入者数"], errors='coerce').fillna(0).astype(int)
    raw_df["総評価数"] = pd.to_numeric(raw_df["総評価数"], errors='coerce').fillna(0).astype(int)

    # 日付フィルタ処理のための関数
    def parse_to_date(val):
        if not isinstance(val, str): return None
        match = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", val)
        if match:
            return datetime.strptime(match.group(0), "%Y.%m.%d").date()
        return None

    # 日付初期値判定用のフラグ
    is_min_date1_default = (min_date1 == past_limit_date)
    is_min_date3_default = (min_date3 == past_limit_date)

    def filter_row(row):
        # 1. 購入者数と総評価数のチェック
        if not (min_buy <= row["購入者数"] <= max_buy): return False
        if not (min_rev <= row["総評価数"] <= max_rev): return False
        
        # 2. 直近販売日1のチェック
        d1 = parse_to_date(row["直近販売日1"])
        if d1:
            if not (min_date1 <= d1 <= max_date1): return False
        else:
            # 日付に変換できない（3ヶ月以上前など）場合、初期状態のままであれば通過させる
            if not is_min_date1_default: return False
            
        # 3. 直近販売日3のチェック
        d3 = parse_to_date(row["直近販売日3"])
        if d3:
            if not (min_date3 <= d3 <= max_date3): return False
        else:
            if not is_min_date3_default: return False
            
        return True

    # フィルタリングの適用
    mask = raw_df.apply(filter_row, axis=1)
    filtered_df = raw_df[mask].copy()
    
    if not filtered_df.empty:
        filtered_df["No."] = range(1, len(filtered_df) + 1)
        
    st.markdown(f"**現在の表示件数:** {len(filtered_df)} 件 / 全体 {len(raw_df)} 件")
    st.dataframe(filtered_df, use_container_width=True, hide_index=True)
    
    excel_data = convert_df_to_excel(filtered_df)
    st.download_button(
        label="📥 絞り込んだデータをExcelでダウンロード",
        data=excel_data,
        file_name=f"creema_research_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
