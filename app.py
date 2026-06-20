import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import time
from urllib.parse import quote
from datetime import datetime, timedelta
import pandas as pd
import io
from concurrent.futures import ThreadPoolExecutor, as_completed

# =============================================
#   デザインとヘッダー設定
# =============================================
st.set_page_config(page_title="Creema市場リサーチツール (高速版)", page_icon="💎", layout="wide")

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
    .stTextInput input, .stNumberInput input, .stDateInput input, div[data-testid="stSelectbox"] div { padding: 6px 10px !important; min-height: 36px !important; height: 36px !important; font-size: 13.5px !important; }
    /* デバッグログ用スタイリング */
    .log-box {
        background-color: #f0f2f6;
        border-radius: 5px;
        padding: 10px;
        font-family: monospace;
        font-size: 12px;
        height: 250px;
        overflow-y: scroll;
        white-space: pre-wrap;
        border: 1px solid #dcdcdc;
        color: #333333;
    }
    </style>
""", unsafe_allow_html=True)

st.title("💎 Creema市場リサーチツール (ハイスピード安定版)")
st.markdown('<hr style="border: none; border-top: 1px solid #e6e6e6; margin-top: 15px; margin-bottom: 25px; padding: 0;">', unsafe_allow_html=True)

# =============================================
#   サイドバー：設定エリア
# =============================================
st.sidebar.header("⚙️ 取得条件設定")
mode = st.sidebar.radio("収集モードを選択してください", ("キーワード検索", "一覧URL直貼り"))

search_keyword = ""
target_url = ""

if mode == "キーワード検索":
    search_keyword = st.sidebar.text_input("🔍 検索キーワードを入力", value="天然石 リング")
    encoded_keyword = quote(search_keyword)
    target_url = f"https://www.creema.jp/listing?q={encoded_keyword}&active=pc_listing-form"
else:
    target_url = st.sidebar.text_input("🔗 Creemaの一覧URLを入力", value="")

max_items = st.sidebar.number_input("🔢 取得する商品件数", min_value=1, max_value=500, value=50, step=10)
start_button = st.sidebar.button("🚀 リサーチを開始する", type="primary")

# =============================================
#   安全なログ管理クラス
# =============================================
class RealTimeLogger:
    def __init__(self):
        self.placeholder = st.empty()
        self.logs = []

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        log_html = f'<div class="log-box">{"<br>".join(self.logs)}</div>'
        self.placeholder.markdown(log_html, unsafe_allow_html=True)

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
#   🎯 特定商品の全販売日を取得（高速化調整版）
# =============================================
def fetch_recent_sales_dates(base_rating_url, target_title, required_count, headers, three_months_ago, task_logs, item_no):
    all_matched_dates = []
    current_page = 1
    current_url = base_rating_url
    max_pages_to_search = 5  

    while current_url and current_page <= max_pages_to_search:
        try:
            res = requests.get(current_url, headers=headers, timeout=8)
            if res.status_code == 403:
                task_logs.append(f"⚠️ [商品{item_no}] 評価P{current_page}でアクセス拒否(403)。速度を落とすサインです。")
                break
            if res.status_code != 200:
                break
            
            soup = BeautifulSoup(res.content, "html.parser")
            blocks = soup.select(".p-creator-rating-rating__content")
            if not blocks:
                break
            
            page_has_valid_date = False
            for block in blocks:
                title_tag = block.select_one(".p-creator-rating-rating__title a")
                if title_tag and title_tag.text.strip() == target_title:
                    voice_date_tag = block.select_one(".p-creator-rating-rating__voice .p-creator-rating-rating__date")
                    if voice_date_tag:
                        date_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", voice_date_tag.text)
                        if date_match:
                            date_str = date_match.group(1)
                            review_date = datetime.strptime(date_str, "%Y.%m.%d")
                            
                            if review_date >= three_months_ago:
                                all_matched_dates.append(review_date)
                                page_has_valid_date = True
            
            if not page_has_valid_date and current_page > 1:
                break

            current_page += 1
            if "?" in base_rating_url:
                current_url = f"{base_rating_url}&page={current_page}"
            else:
                current_url = f"{base_rating_url}?page={current_page}"
                
            time.sleep(0.4)  # ⚡ 待機時間を0.6sから0.4sへ微短縮してテンポ向上
            
        except requests.exceptions.Timeout:
            task_logs.append(f"⏳ [商品{item_no}] 評価P{current_page}で通信タイムアウト。スキップ。")
            break
        except Exception as e:
            task_logs.append(f"❌ [商品{item_no}] 評価P{current_page}でエラー: {str(e)}")
            break
            
    all_matched_dates.sort(reverse=True)
    return [d.strftime("%Y.%m.%d") for d in all_matched_dates]

# =============================================
#   単一商品を解析するコアロジック
# =============================================
def fetch_single_item(item_data, headers, one_month_ago, three_months_ago, item_no):
    task_logs = []
    try:
        link = item_data["link"]
        creator = item_data["creator"]
        title = item_data["title"]
        price = item_data["price"]

        task_logs.append(f"🔄 [商品{item_no}] 解析開始: {title[:15]}...")

        purchase_count = "パス"
        favorite = "取得失敗"
        review = "取得失敗"
        recent_review_display = "0件"  
        first_review_date = "取得失敗" 
        last_page_url = None
        last_voices = []
        recent_sales = ["-", "-", "-"]
        
        detail_res = requests.get(link, headers=headers, timeout=8)
        if detail_res.status_code == 200:
            detail_soup = BeautifulSoup(detail_res.content, "html.parser")
            
            purchase_element = detail_soup.find(string=re.compile(r"(\d+人購入|\d+人以上購入)"))
            if purchase_element:
                purchase_count = purchase_element.strip()
            
            fav_element = detail_soup.find(class_=re.compile(r"js-like-item-number"))
            if fav_element:
                favorite = fav_element.text.strip()
            
            all_text = detail_soup.get_text()
            matches = re.findall(r"[（\(](\d+)[）\)]", all_text)
            if matches:
                review = matches[0]

            rating_link_tag = detail_soup.find("a", href=re.compile(r"rating/sale"))
            if rating_link_tag:
                base_rating_url = "https://www.creema.jp" + rating_link_tag["href"]
                
                buy_num_match = re.search(r"(\d+)", purchase_count)
                required_sales_count = 0
                if buy_num_match:
                    p_num = int(buy_num_match.group(1))
                    required_sales_count = min(p_num, 3) if p_num > 0 else 0
                
                if required_sales_count > 0:
                    task_logs.append(f"  🔍 [商品{item_no}] 直近販売日を検索（目標: {required_sales_count}件）")
                    sorted_dates = fetch_recent_sales_dates(base_rating_url, title, required_sales_count, headers, three_months_ago, task_logs, item_no)
                    
                    for idx in range(required_sales_count):
                        if idx < len(sorted_dates):
                            recent_sales[idx] = sorted_dates[idx]
                        else:
                            recent_sales[idx] = "3ヶ月以上前"
                
                # 直近1ヶ月の評価数解析
                rating_res = requests.get(base_rating_url, headers=headers, timeout=8)
                if rating_res.status_code == 200:
                    rating_soup = BeautifulSoup(rating_res.content, "html.parser")
                    voices = rating_soup.select(".p-creator-rating-rating__voice")
                    last_voices = voices 
                    
                    recent_count = 0
                    for voice in voices:
                        date_tag = voice.select_one(".p-creator-rating-rating__date")
                        if date_tag:
                            date_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", date_tag.text.strip())
                            if date_match and datetime.strptime(date_match.group(1), "%Y.%m.%d") >= one_month_ago:
                                recent_count += 1
                    
                    recent_review_display = "20件以上" if (recent_count >= 20 and len(voices) >= 20) else f"{recent_count}件"

                    all_links = rating_soup.find_all("a", href=True)
                    page_data = []
                    for a_tag in all_links:
                        href = a_tag["href"]
                        p_match = re.search(r"page=(\d+)", href) or re.search(r"/rating/sale/(\d+)", href)
                        if p_match:
                            page_data.append((int(p_match.group(1)), href if href.startswith("http") else "https://www.creema.jp" + href))
                    if page_data:
                        _, last_page_url = max(page_data, key=lambda x: x[0])

                if last_page_url:
                    last_page_res = requests.get(last_page_url, headers=headers, timeout=8)
                    if last_page_res.status_code == 200:
                        last_voices = BeautifulSoup(last_page_res.content, "html.parser").select(".p-creator-rating-rating__voice")
                
                if last_voices:
                    oldest_date = None
                    for voice in last_voices:
                        date_tag = voice.select_one(".p-creator-rating-rating__date")
                        if date_tag:
                            date_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", date_tag.text)
                            if date_match:
                                current_date = datetime.strptime(date_match.group(1), "%Y.%m.%d")
                                if oldest_date is None or current_date < oldest_date: oldest_date = current_date
                    if oldest_date: first_review_date = oldest_date.strftime("%Y.%m.%d")

        task_logs.append(f"✅ [商品{item_no}] 完了")
        result_data = {
            "作家名": creator, "商品名": title, "価格(円)": price, "商品URL": link,
            "お気に入り数": favorite, "購入者数": purchase_count, "総評価数": review,
            "直近1ヶ月の評価数": recent_review_display, "一番初めの評価日": first_review_date,
            "直近販売日1": recent_sales[0], "直近販売日2": recent_sales[1], "直近販売日3": recent_sales[2],
        }
        return result_data, task_logs
    except Exception as e:
        task_logs.append(f"❌ [商品{item_no}] エラーでスキップ: {str(e)}")
        return None, task_logs

# =============================================
#   メインのスクレイピング制御
# =============================================
def scrape_creema_fast(start_url, max_num, logger):
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
    
    logger.log("====== 🕵️ 一覧ページの巡回を開始します ======")
    page_status = st.empty()
    
    while current_url and len(all_item_elements_data) < max_num:
        page_status.info(f" ページ巡回中... 現在 {page_count} ページ目をスキャンしています (収集済リンク: {len(all_item_elements_data)}件)")
        try:
            response = requests.get(current_url, headers=headers, timeout=10)
            if response.status_code == 403:
                logger.log("❌ 一覧ページでアクセス拒否(403)されました。")
                break
            if response.status_code != 200: break
            soup = BeautifulSoup(response.content, "html.parser")
            
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
                time.sleep(1.0) # 一覧ページの遷移を1.2sから1.0sへ調整
            else:
                current_url = None
        except Exception as e:
            logger.log(f"❌ 一覧ページ巡回中にエラー: {str(e)}")
            break
            
    page_status.empty()
    total_found = len(all_item_elements_data)
    
    if total_found == 0:
        logger.log("❌ 有効な商品が1件も見つかりませんでした。")
        return None
        
    logger.log(f"====== 📊 詳細解析スタート (合計: {total_found}件) ======")
    status_text = st.empty()
    progress_bar = st.progress(0)
    
    scraped_data = []
    
    # 🚀 限界突破：並行数を「3」から「5」に引き上げてリクエストを最大化
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_item = {executor.submit(fetch_single_item, item_data, headers, one_month_ago, three_months_ago, i+1): i for i, item_data in enumerate(all_item_elements_data)}
        
        for current_idx, future in enumerate(as_completed(future_to_item), 1):
            result, task_logs = future.result()
            
            for msg in task_logs:
                logger.log(msg)
                
            if result: 
                scraped_data.append(result)
                
            progress_bar.progress(current_idx / total_found)
            status_text.text(f"⏳ 大規模解析中... 完了: {current_idx} / {total_found} 件")
            
    progress_bar.empty()
    status_text.empty()
    logger.log("====== 🎉 全ての解析工程が完了しました！ ======")
    
    if scraped_data:
        for i, item in enumerate(scraped_data, 1): item["No."] = i
        return scraped_data
    return None

# =============================================
#   Excelダウンロード用バイナリ生成
# =============================================
def convert_df_to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="リサーチ結果", index=False)
        worksheet = writer.sheets["リサーチ結果"]
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        header_font = Font(name="Meiryo", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
        data_font = Font(name="Meiryo", size=10)
        thin_border = Border(left=Side(style='thin', color='D9D9D9'), right=Side(style='thin', color='D9D9D9'), top=Side(style='thin', color='D9D9D9'), bottom=Side(style='thin', color='D9D9D9'))
        
        for row in worksheet.iter_rows(min_row=1, max_row=len(df)+1):
            for cell in row:
                cell.border = thin_border
                if cell.row == 1:
                    cell.font = header_font
                    cell.fill = header_fill
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                else:
                    cell.font = data_font
                    if cell.column in [1, 4]: cell.alignment = Alignment(horizontal="right", vertical="center")
                    elif cell.column in [6, 7, 8, 9, 10, 11, 12, 13]: cell.alignment = Alignment(horizontal="center", vertical="center")
                    else: cell.alignment = Alignment(horizontal="left", vertical="center")
        for col in worksheet.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            worksheet.column_dimensions[col[0].column_letter].width = min(max(max_len + 3, 10), 50)
    return output.getvalue()

# =============================================
#   メイン制御とセッション管理
# =============================================
if "raw_data" not in st.session_state:
    st.session_state.raw_data = None

if start_button:
    if mode == "一覧URL直貼り" and not target_url:
        st.error("⚠️ URLを入力してください。")
    else:
        st.subheader("📋 リアルタイム解析ログ（不具合監視用）")
        logger = RealTimeLogger()
        
        cond_text = f"キーワード: {search_keyword}" if mode == "キーワード検索" else f"直貼りURL: {target_url}"
        send_line_notification(cond_text, max_items)
        
        data = scrape_creema_fast(target_url, max_items, logger)
        if data:
            st.session_state.raw_data = data
            st.toast("🎉 取得完了しました！", icon="✅")

if st.session_state.raw_data:
    df_orig = pd.DataFrame(st.session_state.raw_data)
    df_filter = df_orig.copy()
    
    df_filter["_price_num"] = pd.to_numeric(df_filter["価格(円)"], errors='coerce').fillna(0).astype(int)
    df_filter["_fav_num"] = pd.to_numeric(df_filter["お気に入り数"].str.replace(r"\D", "", regex=True), errors='coerce').fillna(0).astype(int)
    df_filter["_buy_num"] = pd.to_numeric(df_filter["購入者数"].str.replace(r"\D", "", regex=True), errors='coerce').fillna(0).astype(int)
    df_filter["_rev_num"] = pd.to_numeric(df_filter["総評価数"].str.replace(r"\D", "", regex=True), errors='coerce').fillna(0).astype(int)
    df_filter["_recent_num"] = pd.to_numeric(df_filter["直近1ヶ月の評価数"].str.replace(r"\D", "", regex=True), errors='coerce').fillna(0).astype(int)
    
    max_price_val = int(df_filter["_price_num"].max()) if not df_filter.empty else 0
    max_fav_val = int(df_filter["_fav_num"].max()) if not df_filter.empty else 0
    max_buy_val = int(df_filter["_buy_num"].max()) if not df_filter.empty else 0
    max_rev_val = int(df_filter["_rev_num"].max()) if not df_filter.empty else 0

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🎯 データ絞り込みフィルター")
    
    st.sidebar.markdown("##### 🪙 金額(円)")
    col_price1, _, col_price2 = st.sidebar.columns([4.5, 1, 4.5], gap="small")
    filter_price_min = col_price1.number_input("🪙 最小", min_value=0, max_value=max_price_val, value=0, key="price_min", label_visibility="collapsed")
    filter_price_max = col_price2.number_input("🪙 最大", min_value=0, max_value=max_price_val, value=max_price_val, key="price_max", label_visibility="collapsed")
    
    st.sidebar.markdown("##### ⭐ お気に入り数")
    col_fav1, _, col_fav2 = st.sidebar.columns([4.5, 1, 4.5], gap="small")
    filter_fav_min = col_fav1.number_input("⭐ 最小", min_value=0, max_value=max_fav_val, value=0, key="fav_min", label_visibility="collapsed")
    filter_fav_max = col_fav2.number_input("⭐ 最大", min_value=0, max_value=max_fav_val, value=max_fav_val, key="fav_max", label_visibility="collapsed")
        
    st.sidebar.markdown("##### 🛒 購入者数")
    col_buy1, _, col_buy2 = st.sidebar.columns([4.5, 1, 4.5], gap="small")
    filter_buy_min = col_buy1.number_input("🛒 最小", min_value=0, max_value=max_buy_val, value=0, key="buy_min", label_visibility="collapsed")
    filter_buy_max = col_buy2.number_input("🛒 最大", min_value=0, max_value=max_buy_val, value=max_buy_val, key="buy_max", label_visibility="collapsed")
        
    st.sidebar.markdown("##### 💬 総評価数")
    col_rev1, _, col_rev2 = st.sidebar.columns([4.5, 1, 4.5], gap="small")
    filter_rev_min = col_rev1.number_input("💬 最小", min_value=0, max_value=max_rev_val, value=0, key="rev_min", label_visibility="collapsed")
    filter_rev_max = col_rev2.number_input("💬 最大", min_value=0, max_value=max_rev_val, value=max_rev_val, key="rev_max", label_visibility="collapsed")
    
    st.sidebar.markdown("##### 📅 直近1ヶ月の評価数")
    filter_recent = st.sidebar.selectbox("📅 直近1ヶ月の評価数", ("すべて", "1件以上", "5件以上", "10件以上", "20件以上"), label_visibility="collapsed")
    
    st.sidebar.markdown("##### ⏱️ 一番初めの評価日")
    col_date1, _, col_date2 = st.sidebar.columns([4.5, 1, 4.5], gap="small")
    filter_date_min = col_date1.date_input("⏱️ 開始", value=datetime(2010, 1, 1).date(), max_value=datetime.now().date(), key="date_min", label_visibility="collapsed")
    filter_date_max = col_date2.date_input("⏱️ 終了", value=datetime.now().date(), max_value=datetime.now().date(), key="date_max", label_visibility="collapsed")

    query_df = df_filter[
        (df_filter["_price_num"] >= filter_price_min) & (df_filter["_price_num"] <= filter_price_max) &
        (df_filter["_fav_num"] >= filter_fav_min) & (df_filter["_fav_num"] <= filter_fav_max) &
        (df_filter["_buy_num"] >= filter_buy_min) & (df_filter["_buy_num"] <= filter_buy_max) &
        (df_filter["_rev_num"] >= filter_rev_min) & (df_filter["_rev_num"] <= filter_rev_max)
    ]
    
    if filter_recent == "1件以上": query_df = query_df[query_df["_recent_num"] >= 1]
    elif filter_recent == "5件以上": query_df = query_df[query_df["_recent_num"] >= 5]
    elif filter_recent == "10件以上": query_df = query_df[query_df["_recent_num"] >= 10]
    elif filter_recent == "20件以上": query_df = query_df[(query_df["_recent_num"] >= 20) | (query_df["直近1ヶ月の評価数"] == "20件以上")]

    def check_date_range(date_str):
        try:
            if date_str == "取得失敗": return False
            return filter_date_min <= datetime.strptime(date_str, "%Y.%m.%d").date() <= filter_date_max
        except: return False
            
    query_df = query_df[query_df["一番初めの評価日"].apply(check_date_range)]
    final_df = query_df.drop(columns=["_price_num", "_fav_num", "_buy_num", "_rev_num", "_recent_num"])
    if not final_df.empty: final_df["No."] = range(1, len(final_df) + 1)
    
    st.success(f"📊 条件に一致した商品: {len(final_df)} 件 / 全件中")
    excel_data = convert_df_to_excel(final_df)
    
    st.download_button(
        label="📥 絞り込んだデータをExcelでダウンロード",
        data=excel_data,
        file_name=f"Creemaリサーチ_絞り込み済_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    st.subheader("👀 絞り込み結果のプレビュー")
    st.dataframe(final_df, use_container_width=True, height=600, column_config={"商品名": st.column_config.TextColumn("商品名", width=250), "商品URL": st.column_config.LinkColumn("商品URL", display_text="ページを開く 🔗")})
