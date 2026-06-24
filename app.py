import io
import re
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from urllib.parse import quote
import numpy as np
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

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
    
    /* 入力フォーム全体のコンパクト化設定 */
    .stTextInput input, .stNumberInput input, .stDateInput input, div[data-testid="stSelectbox"] div { 
        padding: 4px 8px !important; 
        min-height: 32px !important; 
        height: 32px !important; 
        font-size: 13px !important; 
    }
    
    /* フィルター枠内の「ー」「＋」ボタンを完全に非表示にするCSS */
    div[data-testid="stNumberInput"] button {
        display: none !important;
    }
    /* ボタンを消した後の右側余白を詰める調整 */
    div[data-testid="stNumberInput"] div[data-baseline="true"] {
        padding-right: 8px !important;
    }
    
    /* 判定用スタイル */
    .metric-card {
        background-color: #f8f9fa;
        border-left: 5px solid #1f497d;
        padding: 15px;
        border-radius: 4px;
        margin-bottom: 15px;
    }
    .ai-box {
        background-color: #f0f4f8;
        border: 1px solid #d0e2ff;
        padding: 20px;
        border-radius: 6px;
        margin-top: 20px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("💎 Creema市場リサーチツール")
st.markdown('<hr style="border: none; border-top: 1px solid #e6e6e6; margin-top: 15px; margin-bottom: 25px; padding: 0;">', unsafe_allow_html=True)

# =============================================
#   サイドバー：設定エリア
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

max_items = st.sidebar.number_input("🔢 取得する商品件数", min_value=1, max_value=500, value=100, step=10)
start_button = st.sidebar.button("🚀 リサーチを開始する", type="primary")

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
#   メインのスクレイピング制御（自己完結版）
# =============================================
def scrape_creema_fast(start_url, max_num):
    import time
    import random
    import re
    import requests
    from bs4 import BeautifulSoup
    from datetime import datetime, timedelta
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import streamlit as st

    # ----------------------------------------------------
    # 💡 【完全内蔵】1件詳細解析用パーツ（外部依存をゼロに設計）
    # ----------------------------------------------------
    def _internal_fetch_item(item_data, headers, one_month_ago, three_months_ago):
        try:
            link = item_data["link"]
            creator = item_data["creator"]
            title = item_data["title"]
            price = item_data["price"]

            purchase_count = 0  
            favorite = "-"
            review = "-"
            recent_review_display = "0件"  
            first_review_date = "-" 
            last_page_url = None
            last_voices = []
            recent_sales = ["-", "-", "-"]
            description_text = "-" 
            
            try:
                detail_res = requests.get(link, headers=headers, timeout=10)
                if detail_res.status_code == 200:
                    detail_soup = BeautifulSoup(detail_res.content, "html.parser")
                    
                    # 1. 作品紹介文
                    try:
                        desc_element = detail_soup.select_one(".p-item-detail-description, .js-item-description, .p-item-detail__description")
                        if desc_element: description_text = desc_element.text.strip()
                    except: pass

                    # 2. お気に入り数
                    try:
                        fav_element = detail_soup.find(class_=re.compile(r"js-like-item-number"))
                        if fav_element: favorite = fav_element.text.strip()
                    except: pass
                    
                    # 3. 購入者数
                    try:
                        purchase_element = detail_soup.find(string=re.compile(r"(\d+人購入|\d+人以上購入)"))
                        if purchase_element: purchase_count = purchase_element.strip()
                    except: pass
                    
                    # 4. 総評価数
                    rating_link_tag = detail_soup.find("a", href=re.compile(r"rating/sale"))
                    if rating_link_tag and rating_link_tag.text:
                        try:
                            matches = re.search(r"（(\d+)件）", rating_link_tag.text)
                            if matches: review = matches.group(1)
                        except: pass

                    # 5. 評価ページの解析
                    if rating_link_tag:
                        try:
                            base_rating_url = "https://www.creema.jp" + rating_link_tag["href"]
                            
                            # --- 💡 [完全内蔵] 直近販売日取得ロジック ---
                            all_matched_dates = []
                            current_page = 1
                            current_url = base_rating_url
                            clean_target = " ".join(title.strip().split())
                            
                            while current_url and current_page <= 5:  
                                try:
                                    res = requests.get(current_url, headers=headers, timeout=8)
                                    if res.status_code != 200: break
                                    
                                    soup = BeautifulSoup(res.content, "html.parser")
                                    blocks = soup.select(".p-creator-rating-rating__content")
                                    if not blocks: break
                                    
                                    for block in blocks:
                                        title_tags = block.select(".p-creator-rating-rating__title a")
                                        has_target_item = False
                                        for t in title_tags:
                                            if " ".join(t.text.strip().split()) == clean_target:
                                                has_target_item = True
                                                break
                                        
                                        if has_target_item:
                                            voices = block.select(".p-creator-rating-rating__voice")
                                            for voice in voices:
                                                date_tag = voice.select_one(".p-creator-rating-rating__date")
                                                if date_tag:
                                                    date_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", date_tag.text)
                                                    if date_match:
                                                        review_date = datetime.strptime(date_match.group(1), "%Y.%m.%d")
                                                        if review_date >= three_months_ago:
                                                            all_matched_dates.append(review_date)
                                    
                                    all_matched_dates.sort(reverse=True)
                                    if len(all_matched_dates) >= 3: break  
                                    
                                    all_page_dates = []
                                    for date_tag in soup.select(".p-creator-rating-rating__date"):
                                        d_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", date_tag.text)
                                        if d_match: all_page_dates.append(datetime.strptime(d_match.group(1), "%Y.%m.%d"))
                                    if all_page_dates and max(all_page_dates) < three_months_ago: break
                                    
                                    current_page += 1
                                    current_url = f"{base_rating_url}&page={current_page}" if "?" in base_rating_url else f"{base_rating_url}?page={current_page}"
                                    time.sleep(0.1)
                                except:
                                    break
                            
                            all_matched_dates.sort(reverse=True)
                            sorted_dates = [d.strftime("%Y.%m.%d") for d in all_matched_dates[:3]]
                            
                            for idx in range(3):
                                if idx < len(sorted_dates): recent_sales[idx] = sorted_dates[idx]
                                else: recent_sales[idx] = "3ヶ月以上前"
                            # --------------------------------------------

                            # 直近1ヶ月の評価数
                            rating_res = requests.get(base_rating_url, headers=headers, timeout=10)
                            if rating_res.status_code == 200:
                                rating_soup = BeautifulSoup(rating_res.content, "html.parser")
                                voices = rating_soup.select(".p-creator-rating-rating__voice")
                                last_voices = voices 
                                
                                recent_count = 0
                                for voice in voices:
                                    try:
                                        date_tag = voice.select_one(".p-creator-rating-rating__date")
                                        if date_tag:
                                            date_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", date_tag.text.strip())
                                            if date_match and datetime.strptime(date_match.group(1), "%Y.%m.%d") >= one_month_ago:
                                                recent_count += 1
                                    except: pass
                                
                                recent_review_display = "20件以上" if (recent_count >= 20 and len(voices) >= 20) else f"{recent_count}件"

                                # 最初の評価日ページURL探し
                                try:
                                    all_links = rating_soup.find_all("a", href=True)
                                    page_data = []
                                    for a_tag in all_links:
                                        href = a_tag["href"]
                                        p_match = re.search(r"page=(\d+)", href) or re.search(r"/rating/sale/(\d+)", href)
                                        if p_match: page_data.append((int(p_match.group(1)), href if href.startswith("http") else "https://www.creema.jp" + href))
                                    if page_data: _, last_page_url = max(page_data, key=lambda x: x[0])
                                except: pass

                            # 一番古い評価日の解析
                            if last_page_url:
                                try:
                                    last_page_res = requests.get(last_page_url, headers=headers, timeout=10)
                                    if last_page_res.status_code == 200:
                                        last_voices = BeautifulSoup(last_page_res.content, "html.parser").select(".p-creator-rating-rating__voice")
                                except: pass
                            
                            if last_voices:
                                try:
                                    oldest_date = None
                                    for voice in last_voices:
                                        date_tag = voice.select_one(".p-creator-rating-rating__date")
                                        if date_tag:
                                            date_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", date_tag.text)
                                            if date_match:
                                                current_date = datetime.strptime(date_match.group(1), "%Y.%m.%d")
                                                if oldest_date is None or current_date < oldest_date: oldest_date = current_date
                                    if oldest_date: first_review_date = oldest_date.strftime("%Y.%m.%d")
                                except: first_review_date = "解析失敗"
                        except: pass
            except:
                description_text = "通信エラー"

            return {
                "No.": 0, "作家名": creator, "商品名": title, "価格(円)": price, "商品URL": link,
                "お気に入り数": favorite, "購入者数": purchase_count,  
                "直近販売日1": recent_sales[0], "直近販売日2": recent_sales[1], "直近販売日3": recent_sales[2],
                "総評価数": review, "直近1ヶ月の評価数": recent_review_display, "一番初めの評価日": first_review_date,
                "作品紹介文": description_text 
            }
        except:
            return None

    # ----------------------------------------------------
    # メイン処理スタート
    # ----------------------------------------------------
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
    }
    
    today = datetime.now()
    one_month_ago = today - timedelta(days=30)
    three_months_ago = today - timedelta(days=90)
    
    all_item_elements_data = []
    current_url = start_url
    page_count = 1
    detected_market_total = 170000 
    page_status = st.empty()
    
    # 🌟 ステップ1: 商品リンク収集
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
                    
                title = title_tag.text.strip() or (title_tag.find("img")["alt"].strip() if title_tag.find("img") else "")
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
                time.sleep(0.5)
            else:
                current_url = None
        except:
            break
            
    page_status.empty()
    total_found = len(all_item_elements_data)
    if total_found == 0: return None
        
    # 🌟 ステップ2: 詳細解析（安全分割システム）
    status_text = st.empty()
    progress_bar = st.progress(0)
    scraped_data = []
    
    max_workers = 5 if total_found > 300 else 12
    batch_size = 150
    current_idx = 0
    
    for b_idx in range(0, total_found, batch_size):
        batch = all_item_elements_data[b_idx : b_idx + batch_size]
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_item = {
                executor.submit(_internal_fetch_item, item_data, headers, one_month_ago, three_months_ago): item_data 
                for item_data in batch
            }
            
            for future in as_completed(future_to_item):
                result = future.result()
                current_idx += 1
                
                if result: 
                    if "作品紹介文" not in result: result["作品紹介文"] = "取得失敗"
                    scraped_data.append(result)
                
                progress_bar.progress(min(current_idx / total_found, 1.0))
                status_text.text(f"⏳ 大規模解析中... 完了: {current_idx} / {total_found} 件")
                
        if b_idx + batch_size < total_found:
            status_text.text(f"☕️【安全装置】サーバー負荷軽減のため、5秒間休憩しています...（現在 {current_idx}件完了）")
            time.sleep(random.uniform(4.5, 5.5))
            
    progress_bar.empty()
    status_text.empty()
    
    if scraped_data:
        for i, item in enumerate(scraped_data, 1): 
            item["No."] = i
            if "作品紹介文" not in item: item["作品紹介文"] = "取得失敗"
        return {"items": scraped_data, "market_total": detected_market_total}
    return None


# =============================================
#   Excelダウンロード用バイナリ生成
# =============================================
def convert_df_to_excel(df):
    import re
    import io
    import pandas as pd
    
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
                    if cell.column in [1, 4]: 
                        cell.alignment = Alignment(horizontal="right", vertical="center")
                    elif cell.column in [6, 7, 8, 9, 10, 11, 12, 13]: 
                        cell.alignment = Alignment(horizontal="center", vertical="center")
                    else: 
                        cell.alignment = Alignment(horizontal="left", vertical="center")
                        
        for col in worksheet.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            worksheet.column_dimensions[col[0].column_letter].width = min(max(max_len + 3, 10), 50)
            
    return output.getvalue()


# =============================================
#   メイン制御とセッション管理
# =============================================
if "raw_data" not in st.session_state: st.session_state.raw_data = None
if "market_total" not in st.session_state: st.session_state.market_total = 170000
if "target_max_items" not in st.session_state: st.session_state.target_max_items = 100

if start_button:
    if mode == "一覧URL直貼り" and not target_url:
        st.error("⚠️ URLを入力してください。")
    else:
        cond_text = f"キーワード: {search_keyword}" if mode == "キーワード検索" else f"直貼りURL: {target_url}"
        send_line_notification(cond_text, max_items)
        st.session_state.target_max_items = max_items
        
        res_dict = scrape_creema_fast(target_url, max_items)
        if res_dict:
            st.session_state.raw_data = res_dict["items"]
            st.session_state.market_total = res_dict["market_total"]
            st.toast(f"🎉 取得完了しました！（全体総件数: {res_dict['market_total']:,}件）", icon="✅")

if st.session_state.raw_data:
    df_orig = pd.DataFrame(st.session_state.raw_data)
    df_filter = df_orig.copy()
    
    def clean_purchase_count(val):
        if pd.isna(val) or val == 0: return 0
        val_str = str(val).strip()
        num_match = re.search(r"(\d+)", val_str)
        return int(num_match.group(1)) if num_match else 0

    df_filter["_price_num"] = pd.to_numeric(df_filter["価格(円)"], errors='coerce').fillna(0).astype(int)
    df_filter["_buy_num"] = df_filter["購入者数"].apply(clean_purchase_count)
    df_filter["_rev_num"] = pd.to_numeric(df_filter["総評価数"].str.replace(r"\D", "", regex=True), errors='coerce').fillna(0).astype(int)
    df_filter["_recent_num"] = pd.to_numeric(df_filter["直近1ヶ月の評価数"].str.replace(r"\D", "", regex=True), errors='coerce').fillna(0).astype(int)

    # ----------------------------------------------------
    # 🆕 購入者数に応じた「直近販売日」のマスク（- への書き換え）処理
    # ----------------------------------------------------
    # 購入者数が0の場合：販売日1, 2, 3 をすべて「-」に
    df_filter.loc[df_filter["_buy_num"] == 0, ["直近販売日1", "直近販売日2", "直近販売日3"]] = "-"
    
    # 購入者数が1の場合：販売日2, 3 を「-」に
    df_filter.loc[df_filter["_buy_num"] == 1, ["直近販売日2", "直近販売日3"]] = "-"
    
    # 購入者数が2の場合：販売日3 を「-」に
    df_filter.loc[df_filter["_buy_num"] == 2, ["直近販売日3"]] = "-"
    # ----------------------------------------------------

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🎯 データ絞り込みフィルター")
    
    st.sidebar.markdown("##### 🪙 金額(円)")
    col_price1, _, col_price2 = st.sidebar.columns([4.5, 1, 4.5], gap="small")
    filter_price_min = col_price1.number_input("🪙 最小", min_value=0, value=0, key="price_min", label_visibility="collapsed")
    filter_price_max = col_price2.number_input("🪙 最大", min_value=0, value=None, key="price_max", label_visibility="collapsed")
        
    st.sidebar.markdown("##### 🛒 購入者数")
    col_buy1, _, col_buy2 = st.sidebar.columns([4.5, 1, 4.5], gap="small")
    filter_buy_min = col_buy1.number_input("🛒 最小", min_value=0, value=0, key="buy_min", label_visibility="collapsed")
    filter_buy_max = col_buy2.number_input("🛒 最大", min_value=0, value=None, key="buy_max", label_visibility="collapsed")
    
    st.sidebar.markdown("##### 📅 直近販売日３")
    col_sales3_1, _, col_sales3_2 = st.sidebar.columns([4.5, 1, 4.5], gap="small")
    filter_sales3_min = col_sales3_1.date_input("📅 開始", value=None, max_value=datetime.now().date(), key="sales3_min", label_visibility="collapsed")
    filter_sales3_max = col_sales3_2.date_input("📅 終了", value=None, max_value=datetime.now().date(), key="sales3_max", label_visibility="collapsed")
        
    st.sidebar.markdown("##### 💬 ユーザーの総評価数")
    col_rev1, _, col_rev2 = st.sidebar.columns([4.5, 1, 4.5], gap="small")
    filter_rev_min = col_rev1.number_input("💬 最小", min_value=0, value=0, key="rev_min", label_visibility="collapsed")
    filter_rev_max = col_rev2.number_input("💬 最大", min_value=0, value=None, key="rev_max", label_visibility="collapsed")
    
    st.sidebar.markdown("##### 📅 直近1ヶ月の総評価数")
    filter_recent = st.sidebar.selectbox("📅 直近1ヶ月の総評価数", ("すべて", "1件以上", "5件以上", "10件以上", "20件以上"), label_visibility="collapsed")

    query_df = df_filter.copy()
    if filter_price_min is not None: query_df = query_df[query_df["_price_num"] >= filter_price_min]
    if filter_price_max is not None: query_df = query_df[query_df["_price_num"] <= filter_price_max]
    if filter_buy_min is not None: query_df = query_df[query_df["_buy_num"] >= filter_buy_min]
    if filter_buy_max is not None: query_df = query_df[query_df["_buy_num"] <= filter_buy_max]
    if filter_rev_min is not None: query_df = query_df[query_df["_rev_num"] >= filter_rev_min]
    if filter_rev_max is not None: query_df = query_df[query_df["_rev_num"] <= filter_rev_max]
    
    def check_sales3_date_range(date_str):
        # 開始も終了も「未指定(None)」なら、文字データ（3ヶ月以上前など）も含めてすべて表示する
        if filter_sales3_min is None and filter_sales3_max is None: return True
        # どちらかが指定されている場合は、日付以外の文字データは除外する
        if date_str in ["-", "3ヶ月以上前", "取得失敗"]: return False
        try:
            target_dt = datetime.strptime(date_str, "%Y.%m.%d").date()
            return (filter_sales3_min is None or target_dt >= filter_sales3_min) and (filter_sales3_max is None or target_dt <= filter_sales3_max)
        except: return False
            
    query_df = query_df[query_df["直近販売日3"].apply(check_sales3_date_range)]
    if filter_recent == "1件以上": query_df = query_df[query_df["_recent_num"] >= 1]
    elif filter_recent == "5件以上": query_df = query_df[query_df["_recent_num"] >= 5]
    elif filter_recent == "10件以上": query_df = query_df[query_df["_recent_num"] >= 10]
    elif filter_recent == "20件以上": query_df = query_df[(query_df["_recent_num"] >= 20) | (query_df["直近1ヶ月の評価数"] == "20件以上")]

    query_df["購入者数"] = query_df["_buy_num"]
    final_df = query_df.drop(columns=["_price_num", "_buy_num", "_rev_num", "_recent_num"])
    
    if "作品紹介文" not in final_df.columns:
        final_df["作品紹介文"] = "データなし"
        
    final_df = final_df.rename(columns={"総評価数": "ユーザーの総評価数", "直近1ヶ月の評価数": "直近1ヶ月の総評価数"})
    
    target_columns = [
        "No.", "作家名", "商品名", "価格(円)", "商品URL", "お気に入り数", "購入者数", 
        "直近販売日1", "直近販売日2", "直近販売日3", "ユーザーの総評価数", 
        "直近1ヶ月の総評価数", "一番初めの評価日", "作品紹介文"
    ]
    
    final_df = final_df.reindex(columns=target_columns)
    if not final_df.empty: final_df["No."] = range(1, len(final_df) + 1)
        
    st.success(f"📊 条件に一致した商品: {len(final_df)} 件 / 全件中")
    excel_data = convert_df_to_excel(final_df)
    
    st.download_button(
        label="📥 絞り込んだデータをExcelでダウンロード",
        data=excel_data,
        file_name=f"Creemaリサーチ_絞り込み済_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# =================================================================
# 👀 絞り込み結果のプレビュー
# =================================================================

if "final_df" in locals() and final_df is not None and not final_df.empty:

    st.subheader("👀 絞り込み結果のプレビュー")

    display_df = (
        final_df.drop(columns=["作品紹介文"])
        if "作品紹介文" in final_df.columns
        else final_df
    )

    st.dataframe(
        display_df,
        use_container_width=True,
        height=350,
        hide_index=True,
        column_config={
            "商品名": st.column_config.TextColumn("商品名", width=250),
            "商品URL": st.column_config.LinkColumn("商品URL", display_text="ページを開く 🔗")
        }
    )

    # タイトル・紹介文プロンプト用に、検索上位10件を保存
    candidate_items = final_df.head(10).copy()
    st.session_state["candidate_items"] = candidate_items

    # =============================================
    #   📊 売れやすさ計算 (詳細版)
    # =============================================
    total_raw_count = len(st.session_state.raw_data)
    st.markdown("---")
    st.subheader("📊 独立マーケット分析（売れやすさ計算）")
    
    if total_raw_count < 10:
        st.warning("⚠️ 十分な解析を行うには、少なくとも10件以上の商品データが必要です。")
    else:
        if st.button("📊 売れやすさ指標を計算する", type="secondary"):
            st.session_state.show_calculator = True
            
        if st.session_state.get("show_calculator", False):
            total_market_items = max(1, int(st.session_state.market_total))
            calc_one_month_ago = datetime.now() - timedelta(days=30)
            calc_three_months_ago = datetime.now() - timedelta(days=90)
            
            total_artists_count = len(st.session_state.raw_data)
            under_1000_count, active_under_1000_count, total_recent_sales_3months = 0, 0, 0
            
            for item in st.session_state.raw_data:
                try: r_num = int(re.sub(r"\D", "", str(item["総評価数"])))
                except: r_num = 0
                
                s1_str = item["直近販売日1"]
                is_s1_active_1month, is_s1_active_3months = False, False
                if s1_str not in ["-", "3ヶ月以上前", "取得失敗"]:
                    try:
                        s1_dt = datetime.strptime(s1_str, "%Y.%m.%d")
                        if s1_dt >= calc_one_month_ago: is_s1_active_1month = True
                        if s1_dt >= calc_three_months_ago: is_s1_active_3months = True
                    except: pass
                
                if is_s1_active_3months: total_recent_sales_3months += 1
                if r_num <= 1000:
                    under_1000_count += 1
                    if is_s1_active_1month: active_under_1000_count += 1

            ratio_3months_sales = (total_recent_sales_3months / total_artists_count) if total_artists_count > 0 else 0.0
            ratio_active_vs_total = (active_under_1000_count / total_artists_count) if total_artists_count > 0 else 0.0
            ratio_active_vs_general = (active_under_1000_count / under_1000_count) if under_1000_count > 0 else 0.0

            if ratio_3months_sales <= 0.50:
                judge_title, color = "❄️ お休み市場（需要低迷、または停滞）", "#F8D7DA"
                judge_desc = f"直近3ヶ月以内に販売が動いている商品が、市場全体の {ratio_3months_sales*100:.1f}%（基準50%以下）しかありません。市場全体の動きが非常に鈍く、需要が一時的に冷え込んでいるか、季節外れの可能性があります。別のキーワードでのリサーチをお勧めします。"
                final_score = min(max(int((ratio_3months_sales / 0.50) * 30), 0), 30)
            elif (ratio_active_vs_total <= 0.15) or (ratio_active_vs_general <= 0.30):
                judge_title, color = "⚖️ レッドオーシャン（大手が強すぎる市場）", "#FFF3CD"
                judge_desc = f"直近1ヶ月以内に売れている一般作家の割合が『全体に対して {ratio_active_vs_total*100:.1f}%（基準15%以下）』または『一般作家の中で {ratio_active_vs_general*100:.1f}%（基準30%以下）』となっています。上位や需要のほとんどを大手が独占しており、一般作家が普通に参入しても埋もれやすい過密市場です。差別化戦略が必須となります。"
                final_score = min(max(30 + int(min(ratio_active_vs_total/0.15, ratio_active_vs_general/0.30) * 20), 30), 50)
            else:
                market_bonus = 35 if total_market_items <= 500 else (20 if total_market_items <= 3000 else (5 if total_market_items <= 20000 else max(-int(np.log10(total_market_items / 20000) * 12), -25)))
                final_score = min(max(int((ratio_active_vs_general * 60) + 30 + market_bonus), 51), 100) 
                if final_score >= 75:
                    judge_title, color = "🔥 激アツ（超おすすめ市場）", "#D4EDDA"
                    judge_desc = f"全体の競合件数（{total_market_items:,}件）が適正、かつ一般作家の生存率が非常に高い『理想的なお宝市場』です。大手に需要を吸い尽くされておらず、新しく商品を出しても上位表示や即売れを狙えるチャンスが極めて高い状態です。"
                else:
                    judge_title, color = "✨ 狙い目（十分にチャンスあり）", "#CCE5FF"
                    judge_desc = f"適度に市場が回転しており、一般作家でも十分に売上を立てられる健全な市場です。独自のタイトルワークや見せ方で攻めることで、さらに高い確率でファンを掴めます。"

            st.markdown(f"""
                <div class="metric-card" style="background-color: {color}; border-left-color: #111111;">
                    <h3 style="margin-top:0;">分析結果スコア: <span style="font-size:36px; font-weight:bold;">{final_score}</span> / 100点</h3>
                    <h4>判定：{judge_title}</h4>
                    <p style="font-size:14px; margin-bottom:5px;"><b>🔍 新・判定ロジック算出内訳:</b></p>
                    <ul>
                        <li>自動検出された市場総件数: <b>{total_market_items:,} 件</b></li>
                        <li>📅 <b>直近3ヶ月以内の販売商品割合（基準>50%）: <span style="font-size:15px; font-weight:bold;">{ratio_3months_sales*100:.1f}%</span></b> （{total_recent_sales_3months}件 / {total_artists_count}件中）</li>
                        <li>解析対象内の一般作家（評価1000以下）: <b>{under_1000_count} 件 / {total_artists_count}件中</b></li>
                        <li>直近1ヶ月以内に動いている一般作家: <b>{active_under_1000_count} 件</b></li>
                        <li>📈 <b>対全体比率（基準>15%）: <span style="font-size:15px; font-weight:bold;">{ratio_active_vs_total*100:.1f}%</span></b></li>
                        <li>🎯 <b>対一般作家比率（基準>30%）: <span style="font-size:15px; font-weight:bold;">{ratio_active_vs_general*100:.1f}%</span></b></li>
                    </ul>
                    <p style="font-size:14.5px; line-height:1.6; background:rgba(255,255,255,0.5); padding:10px; border-radius:4px; margin-top:10px;"><b>💡 総評:</b><br>{judge_desc}</p>
                </div>
            """, unsafe_allow_html=True)

    # =============================================
    # 🤖 👑 Gemini作品タイトル提案エリア (復活・修正部分)
    # =============================================
# session_state から検索結果を取り出す
saved_candidate_items = st.session_state.get("candidate_items", None)

# 検索結果がある場合だけ、タイトル・紹介文作成エリアを表示
if saved_candidate_items is not None and not saved_candidate_items.empty:

    candidate_items = saved_candidate_items

    st.subheader("🙆 作品タイトル・紹介文のプロンプト作成")
    st.write("市場の人気を参考に、タイトルや紹介文を作成します。")

    st.caption(
        "作品タイトルや紹介文の精度を上げるために、カテゴリ・素材・サイズ・使いやすさ・使用シーン・こだわりをできるだけ具体的に入力してください。"
    )

    default_work_description = """商品名：
例）帆布のトートバッグ／名入れできる木製キーホルダー／刺繍のブローチ／結婚式のウェルカムボード

商品カテゴリ：
例）アクセサリー／バッグ／財布／ポーチ／インテリア雑貨／ベビー用品／ペット用品／食器／洋服／紙もの／ウェディングアイテム／食品／素材・パーツ など

主な素材：
例）布、帆布、リネン、革、木材、ガラス、陶器、紙、金属、天然石、レジン、刺繍糸、ドライフラワー など

色・雰囲気：
例）ナチュラル、くすみカラー、北欧風、アンティーク調、シンプル、上品、かわいい、落ち着いた色合い など

サイズ：
例）縦〇cm×横〇cm、容量〇ml、A4対応、手のひらサイズ、子ども用、大人用 など

デザインの特徴：
例）シンプルで使いやすい、名入れできる、軽い、持ち運びやすい、飾るだけで雰囲気が出る、季節感がある など

機能・使いやすさ：
例）ポケット付き、洗える、軽量、折りたためる、耐水性がある、金具が丈夫、電子レンジ対応、食洗機対応 など

こだわりポイント：
例）素材選びにこだわっています。毎日使いやすいように、軽さと丈夫さのバランスを意識して作りました。

ハンドメイドならではの魅力：
例）一点ずつ手作業で仕上げています。色味や形に少しずつ個体差があり、手仕事ならではの温かみがあります。

訳あり・注意点があれば：
例）天然素材のため、色味や木目に個体差があります。手作業のため、サイズに多少の誤差が出る場合があります。

おすすめしたい人：
例）自分用に特別感のあるものを探している方、日常で使いやすいものが欲しい方、大切な人へのギフトを探している方

使用シーン：
例）普段使い、通勤、通学、休日のお出かけ、結婚式、誕生日、出産祝い、新生活、母の日、クリスマス など

ギフト向きか：
例）名入れやラッピング対応ができるため、誕生日や記念日のプレゼントにもおすすめです。

価格に見合う理由：
例）丈夫な素材を使っている、手作業に時間をかけている、長く使える、オーダー対応ができる、希少な素材を使っている など

作品に込めた想い：
例）毎日の暮らしの中で、使うたびに少し気分が上がるような作品を目指して作りました。
"""

    my_work_description = st.text_area(
        "📝 あなたの作品の説明・特徴・こだわり",
        value=default_work_description,
        height=420,
        help="分かる範囲で入力してください。空欄があっても大丈夫です。"
    )

    # ここから下に、
    # 「🚀 検索上位を狙うタイトルプロンプトを作成」ボタン
    # 「✍️ 作品紹介文（説明文）のプロンプト作成」
    # を入れる
        
# =================================================================
# 🛍️ ボタン1: 市場10選を分析してタイトルを提案してもらう
# =================================================================        
import textwrap

# candidate_items がすでに作られている場合は、session_state に保存しておく
# ※ 検索・絞り込み処理のあとに candidate_items ができている前提です
if "candidate_items" in locals() and candidate_items is not None and not candidate_items.empty:
    st.session_state["candidate_items"] = candidate_items

# session_state から検索結果を取り出す
saved_candidate_items = st.session_state.get("candidate_items", None)

# 💡 検索後（データが存在する場合）のみエリア全体を表示
if saved_candidate_items is not None and not saved_candidate_items.empty:

    candidate_items = saved_candidate_items

    generate_btn = st.button(
        "🚀 検索上位を狙うタイトルプロンプトを作成",
        type="primary"
    )

    if generate_btn:
        with st.spinner("📝 AI用のプロンプトを作成中..."):

            # 10件の売れ筋データ（candidate_items）からタイトル一覧のテキストを作成
            items_summary = ""

            for display_no, (_, row) in enumerate(candidate_items.iterrows(), start=1):
                item_name = row.get("商品名", "商品名不明")
                buy_num = row.get("_buy_num", "不明")

                items_summary += f"・人気商品{display_no}: {item_name}（購入者数: {buy_num}人）\n"

            # ChatGPTやGeminiにそのまま貼り付けられる完成形プロンプトを組み立て
            final_prompt = textwrap.dedent(f"""
            あなたは、Creema・minneなどのハンドメイドマーケットで売れる商品ページを分析し、
            検索上位に表示されやすく、かつ購入につながる商品タイトルを作る専門家です。

            以下の【分析対象：人気商品のタイトル一覧】と【出品する作品の情報】をもとに、
            Creemaで検索されやすく、クリックされやすく、購入されやすい商品タイトルを作成してください。

            ---
            【分析対象：人気商品のタイトル一覧】
            {items_summary}
            ---

            【出品する作品の情報】
            ■作品の説明・特徴・こだわり:
            {my_work_description}
            ---

            # 重要な前提

            Creemaでは、雰囲気だけのおしゃれなタイトルよりも、
            「何の商品か」
            「どんな素材・特徴があるか」
            「どんな場面で使えるか」
            「購入前の不安が解消されるか」
            がタイトル内で分かる商品の方が、検索にも購入にもつながりやすいです。

            特に、人気商品には以下の傾向があります。

            ・タイトル前半に、検索されやすいメインキーワードが入っている
            ・商品カテゴリが一目で分かる
            ・素材、用途、機能、安心要素が自然に入っている
            ・「かわいい」「おしゃれ」だけではなく、買う理由が伝わる
            ・ギフト、普段使い、季節、イベントなどの使用シーンが分かる
            ・高価格帯の商品は、素材の良さ、手間、希少性、長く使える理由が伝わる
            ・検索される言葉と、作品の世界観のバランスが取れている

            ---

            # タイトル作成で重視すること

            ## 検索上位を狙う条件

            ・タイトルの前半に、検索されやすいメインキーワードを入れる
            ・商品カテゴリが一目で分かる言葉を必ず入れる

            例：
            アクセサリー、バッグ、財布、ポーチ、インテリア雑貨、食器、洋服、ベビー用品、ペット用品、紙もの、ウェディングアイテム、食品、素材、パーツ など

            ・素材名、色、デザイン特徴、用途、機能、安心要素を自然に入れる
            ・「かわいい」「きれい」「上品」だけで終わらせない
            ・タイトルは40〜55文字前後を目安にする
            ・「｜」「【】」を使って、読みやすく区切る
            ・重要キーワードはなるべくタイトル前半に置く
            ・検索されそうな一般名詞を優先し、詩的すぎる言葉だけのタイトルにしない

            ## 購入されやすくする条件

            ・お気に入りだけで終わらず、「今買う理由」が伝わるタイトルにする
            ・使用シーンが分かる言葉を入れる

            例：
            誕生日、母の日、父の日、敬老の日、結婚式、出産祝い、新生活、通勤、通学、普段使い、ギフト、プレゼント、自分へのご褒美 など

            ・購入前の不安を減らす言葉を入れる

            例：
            軽量、洗える、A4対応、名入れ可、サイズ調整可、選べる、送料無料、ラッピング対応、オーダー可、電子レンジ対応、食洗機対応、金属アレルギー対応 など

            ・高価格帯の商品は、素材の良さ、手仕事感、希少性、長く使える理由が伝わるようにする
            ・食品、美容、健康、天然石、アロマ、スピリチュアル系の商品では、効果効能を断定しすぎず、自然で信頼感のある表現にする
            ・商品内容と関係のないキーワードは入れない

            ---

            # 出力してほしい内容

            ## 1. 人気商品のタイトル分析

            以下の観点で、分析してください。

            ### よく使われているキーワード

            人気タイトルの中から、特に重要度が高いキーワードを5〜10個抽出してください。

            それぞれについて、
            ・なぜ検索に強いのか
            ・なぜ購入につながりやすいのか
            を説明してください。

            ### タイトル構成の傾向

            人気商品のタイトルが、どのような順番でキーワードを並べているか分析してください。

            例：
            ・商品カテゴリ → 素材 → 用途
            ・素材 → 商品カテゴリ → ギフト訴求
            ・特徴 → 商品カテゴリ → 安心要素
            ・【フック】＋商品名＋使用シーン
            ・名入れ／オーダー要素 → 商品カテゴリ → 記念日訴求
            ・季節感 → 商品カテゴリ → 暮らしのシーン

            ### 真似すべき点

            出品する作品に取り入れるべき要素を、具体的に教えてください。

            ### 真似しない方がいい点

            人気商品のタイトルの中でも、
            出品する作品には無理に入れない方がいい要素があれば教えてください。

            ---

            ## 2. 出品作品の検索キーワード整理

            出品する作品情報から、タイトルに入れるべきキーワードを分類してください。

            ### メインキーワード

            検索で最も重要な言葉を3〜5個出してください。

            例：
            商品カテゴリ名、素材名、用途名、モチーフ名、作品ジャンル名など

            ### サブキーワード

            素材、色、形、サイズ、デザイン、雰囲気、機能、使いやすさに関する言葉を5〜10個出してください。

            ### 購入訴求キーワード

            ギフト、普段使い、季節、イベント、悩み解消、安心感、便利さにつながる言葉を5〜10個出してください。

            ### 入れない方がいいキーワード

            商品と関係が薄い、検索には強そうでも誤解を招く言葉があれば教えてください。

            ---

            ## 3. 新作商品タイトル案

            以下の切り口で、合計15案作ってください。

            ### A. 検索上位重視タイトル 5案

            検索されやすいキーワードを前半に入れたタイトルにしてください。

            ### B. 購入率重視タイトル 5案

            使用シーン、ギフト、安心要素、買う理由が伝わるタイトルにしてください。

            ### C. 世界観＋検索バランス型タイトル 5案

            作品の雰囲気やこだわりを残しつつ、検索にも弱くならないタイトルにしてください。

            ---

            # タイトル作成ルール

            ・各タイトルは40〜55文字前後を目安にする
            ・短すぎるタイトルは避ける
            ・長すぎて読みにくいタイトルも避ける
            ・最初の15文字以内に、できるだけ重要キーワードを入れる
            ・商品カテゴリを必ず入れる
            ・「｜」「【】」を適度に使い、見やすくする
            ・同じ言葉を不自然に繰り返さない
            ・商品内容と違う誇大表現はしない
            ・効果効能を断定しない
            ・購入者が安心して買える、上品で信頼感のある表現にする
            ・人気商品のタイトルをそのままコピーしない

            ---

            ## 4. 一番おすすめのタイトル

            15案の中から、一番おすすめのタイトルを1つ選んでください。

            その理由を、以下の観点で説明してください。

            ・検索に強い理由
            ・クリックされやすい理由
            ・購入につながりやすい理由
            ・出品作品の魅力が伝わる理由
            ・改善するとしたらどこか

            ---

            ## 5. タイトル改善アドバイス

            最後に、出品者が今後タイトルを作る時に使えるように、
            この作品に合う「タイトルの型」を3つ作ってください。

            例：
            ・素材名＋商品カテゴリ｜使用シーン＋安心要素
            ・商品カテゴリ＋特徴｜ギフト用途＋使いやすさ
            ・色や雰囲気＋商品カテゴリ｜こだわりポイント＋使用シーン
            ・名入れ／オーダー要素＋商品カテゴリ｜記念日・ギフト訴求
            ・季節感＋商品カテゴリ｜暮らしに取り入れる場面

            ---

            注意：
            分析対象の人気商品タイトルをそのままコピーしないでください。
            人気商品の「言葉の使い方」「キーワードの並び順」「購入につながる訴求」を参考にしながら、
            出品する作品に合った自然なタイトルを作ってください。
            """).strip()

            # 完成したプロンプトを表示
            st.subheader("📋 AI用コピーテキストの作成完了")
            st.success("✨ 下の枠内のテキストをすべてコピーして、ChatGPTやGeminiのチャット欄に貼り付けてください。")

            st.text_area(
                "以下の文章を丸ごとコピーしてください：",
                value=final_prompt,
                height=450,
                key="title_prompt_area"
            )


import json

# =================================================================
# ✍️ ボタン2: 市場10選を分析して作品紹介文を提案してもらう
# =================================================================

saved_candidate_items = st.session_state.get("candidate_items", None)

if saved_candidate_items is not None and not saved_candidate_items.empty:

    candidate_items = saved_candidate_items

    st.write("---")
    st.subheader("✍️ 作品紹介文（説明文）のプロンプト作成")

    my_product_title = st.text_input(
        "🏷️ 出品する作品のタイトル（決まっている場合や、上記で決めたタイトルを入力してください）",
        value="",
        help="AIが紹介文を作成する際に、このタイトルとの整合性を意識して文章を作ります。",
        key="my_product_title_input"
    )

    generate_desc_btn = st.button(
        "🚀 市場10選を分析して作品紹介文プロンプトを作成",
        type="primary",
        key="generate_desc_prompt_btn"
    )

    if generate_desc_btn:
        with st.spinner("🕵️‍♂️ 市場10選の作品ページから、紹介文を読み込んでいます（数秒かかります）..."):

            descriptions_summary = ""

            for display_no, (_, row) in enumerate(candidate_items.iterrows(), start=1):
                item_name = row.get("商品名", "商品名不明")

                item_url = row.get(
                    "商品URL",
                    row.get(
                        "URL",
                        row.get(
                            "url",
                            row.get("作品URL", None)
                        )
                    )
                )

                if item_url and isinstance(item_url, str) and item_url.startswith("/"):
                    item_url = f"https://www.creema.jp{item_url}"

                cleaned_desc = "（紹介文の取得に失敗しました）"

                if item_url:
                    try:
                        headers = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                                          "Chrome/120.0.0.0 Safari/537.36"
                        }

                        response = requests.get(item_url, headers=headers, timeout=10)

                        if response.status_code == 200:
                            soup = BeautifulSoup(response.text, "html.parser")
                            desc_element = soup.find("div", class_="p-item-detail-description")

                            if desc_element:
                                raw_text = desc_element.get_text("\n", strip=True)
                                cleaned_desc = re.sub(r"\n{3,}", "\n\n", raw_text)

                    except Exception as e:
                        cleaned_desc = f"（通信エラーにより取得失敗: {str(e)}）"

                descriptions_summary += (
                    f"■人気商品{display_no}: {item_name}\n"
                    f"【紹介文】:\n{cleaned_desc}\n\n"
                )

            final_desc_prompt = textwrap.dedent(f"""
            あなたは、Creema・minneなどのハンドメイドマーケットで売れる商品ページを分析し、
            検索上位に表示されやすく、かつ購入につながる作品紹介文を作る専門家です。

            以下の【分析対象：人気商品の紹介文一覧】と【出品する作品の情報】をもとに、
            お気に入りだけで終わらず、購入につながりやすい作品紹介文を作成してください。

            ---
            【分析対象：人気商品の紹介文一覧】
            {descriptions_summary}
            ---

            【出品する作品の情報】
            ■作品のタイトル:
            {my_product_title}

            ■作品の説明・特徴・こだわり:
            {my_work_description}
            ---

            # 重要な前提

            Creemaやminneでは、作品紹介文がただ長いだけでは購入につながりません。

            大切なのは、冒頭で
            「これは何の商品か」
            「誰におすすめか」
            「どんな場面で使えるか」
            「買う前の不安が解消されるか」
            がすぐに伝わることです。

            人気商品の紹介文を分析し、
            出品ページにそのまま使える作品紹介文を3パターン作成してください。

            ## 出力内容

            1. 人気商品の紹介文分析
            ・文章構成の傾向
            ・購入につながる表現
            ・お気に入り止まりを防ぐポイント
            ・今回の作品に取り入れるべき要素

            2. 出品作品の魅力整理
            ・作品の一番の魅力
            ・想定される購入者
            ・購入者の悩みや願望
            ・購入後の未来
            ・購入前の不安と解消ポイント

            3. 作品紹介文の提案
            A. 検索キーワード重視
            B. 購入率重視
            C. 世界観＋購入訴求バランス型

            4. 検索対策キーワード一覧
            Creemaやminneで検索されやすいキーワードを20個以上、スペース区切りで出してください。

            ## 文章ルール

            ・冒頭3行で魅力が伝わるようにする
            ・1〜2文ごとに空行を入れる
            ・見出しを使ってスマホで読みやすくする
            ・素材、サイズ、使用シーン、ギフト、注意点を自然に入れる
            ・効果効能を断定しない
            ・人気商品の文章をそのままコピーしない
            ・上品で丁寧、信頼感のある文章にする
            """).strip()

            st.subheader("📋 【作品紹介文用】AI用コピーテキスト")
            st.success("✨ 作品紹介文用のプロンプトが完成しました！下の枠内のテキストをすべてコピーして、ChatGPTやGeminiに貼り付けてください。")

            st.text_area(
                "以下の文章を丸ごとコピーしてください：",
                value=final_desc_prompt,
                height=500,
                key="desc_prompt_area"
            )

            js_safe_prompt = json.dumps(final_desc_prompt)

            copy_button_html = f"""
            <div style="margin-top: -10px; margin-bottom: 20px;">
                <button id="copy-desc-btn" style="
                    background-color: #FF4B4B;
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    font-size: 14px;
                    font-weight: bold;
                    border-radius: 4px;
                    cursor: pointer;
                    transition: background-color 0.3s;
                    width: 100%;
                ">📋 このプロンプトをワンクリックでコピーする</button>
            </div>

            <script>
            document.getElementById('copy-desc-btn').addEventListener('click', function() {{
                const textToCopy = {js_safe_prompt};

                navigator.clipboard.writeText(textToCopy).then(function() {{
                    const btn = document.getElementById('copy-desc-btn');
                    btn.innerText = '✅ コピーが完了しました！';
                    btn.style.backgroundColor = '#28a745';

                    setTimeout(function() {{
                        btn.innerText = '📋 このプロンプトをワンクリックでコピーする';
                        btn.style.backgroundColor = '#FF4B4B';
                    }}, 2000);
                }}).catch(function(err) {{
                    alert('コピーに失敗しました。テキストエリアから直接コピーしてください。');
                }});
            }});
            </script>
            """

            st.components.v1.html(copy_button_html, height=60)
