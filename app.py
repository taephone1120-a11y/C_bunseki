import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import time
from urllib.parse import quote
from datetime import datetime, timedelta
import pandas as pd
import io
import numpy as np
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
    .stTextInput input, .stNumberInput input, .stDateInput input, div[data-testid="stSelectbox"] div { padding: 6px 10px !important; min-height: 36px !important; height: 36px !important; font-size: 13.5px !important; }
    
    /* 判定用スタイル */
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
#   🎯 特定商品の全販売日を取得
# =============================================
def fetch_recent_sales_dates(base_rating_url, target_title, required_count, headers, three_months_ago):
    all_matched_dates = []
    current_page = 1
    current_url = base_rating_url
    max_pages_to_search = 5  

    while current_url and current_page <= max_pages_to_search:
        try:
            res = requests.get(current_url, headers=headers, timeout=8)
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
                
            time.sleep(0.4)  
            
        except:
            break
            
    all_matched_dates.sort(reverse=True)
    return [d.strftime("%Y.%m.%d") for d in all_matched_dates]

# =============================================
#   単一商品を解析するコアロジック
# =============================================
def fetch_single_item(item_data, headers, one_month_ago, three_months_ago):
    try:
        link = item_data["link"]
        creator = item_data["creator"]
        title = item_data["title"]
        price = item_data["price"]

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
                    sorted_dates = fetch_recent_sales_dates(base_rating_url, title, required_sales_count, headers, three_months_ago)
                    
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

        result_data = {
            "No.": 0,
            "作家名": creator,
            "商品名": title,
            "価格(円)": price,
            "商品URL": link,
            "お気に入り数": favorite,
            "購入者数": purchase_count,
            "直近販売日1": recent_sales[0],
            "直近販売日2": recent_sales[1],
            "直近販売日3": recent_sales[2],
            "総評価数": review,
            "直近1ヶ月の評価数": recent_review_display,
            "一番初めの評価日": first_review_date,
        }
        return result_data
    except:
        return None

# =============================================
#   メインのスクレイピング制御
# =============================================
def scrape_creema_fast(start_url, max_num):
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
    
    page_status = st.empty()
    
    while current_url and len(all_item_elements_data) < max_num:
        page_status.info(f" ページ巡回中... 現在 {page_count} ページ目をスキャンしています (収集済リンク: {len(all_item_elements_data)}件)")
        try:
            response = requests.get(current_url, headers=headers, timeout=10)
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
                time.sleep(1.0)
            else:
                current_url = None
        except:
            break
            
    page_status.empty()
    total_found = len(all_item_elements_data)
    
    if total_found == 0:
        return None
        
    status_text = st.empty()
    progress_bar = st.progress(0)
    
    scraped_data = []
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_item = {executor.submit(fetch_single_item, item_data, headers, one_month_ago, three_months_ago): i for i, item_data in enumerate(all_item_elements_data)}
        
        for current_idx, future in enumerate(as_completed(future_to_item), 1):
            result = future.result()
            if result: 
                scraped_data.append(result)
                
            progress_bar.progress(current_idx / total_found)
            status_text.text(f"⏳ 大規模解析中... 完了: {current_idx} / {total_found} 件")
            
    progress_bar.empty()
    status_text.empty()
    
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
        cond_text = f"キーワード: {search_keyword}" if mode == "キーワード検索" else f"直貼りURL: {target_url}"
        send_line_notification(cond_text, max_items)
        
        data = scrape_creema_fast(target_url, max_items)
        if data:
            st.session_state.raw_data = data
            st.toast("🎉 取得完了しました！", icon="✅")

if st.session_state.raw_data:
    df_orig = pd.DataFrame(st.session_state.raw_data)
    df_filter = df_orig.copy()
    
    df_filter["_price_num"] = pd.to_numeric(df_filter["価格(円)"], errors='coerce').fillna(0).astype(int)
    df_filter["_buy_num"] = pd.to_numeric(df_filter["購入者数"].str.replace(r"\D", "", regex=True), errors='coerce').fillna(0).astype(int)
    df_filter["_rev_num"] = pd.to_numeric(df_filter["総評価数"].str.replace(r"\D", "", regex=True), errors='coerce').fillna(0).astype(int)
    df_filter["_recent_num"] = pd.to_numeric(df_filter["直近1ヶ月の評価数"].str.replace(r"\D", "", regex=True), errors='coerce').fillna(0).astype(int)
    
    max_price_val = int(df_filter["_price_num"].max()) if not df_filter.empty else 0
    max_buy_val = int(df_filter["_buy_num"].max()) if not df_filter.empty else 0
    max_rev_val = int(df_filter["_rev_num"].max()) if not df_filter.empty else 0

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🎯 データ絞り込みフィルター")
    
    # 1. 金額(円)
    st.sidebar.markdown("##### 🪙 金額(円)")
    col_price1, _, col_price2 = st.sidebar.columns([4.5, 1, 4.5], gap="small")
    filter_price_min = col_price1.number_input("🪙 最小", min_value=0, max_value=max_price_val, value=0, key="price_min", label_visibility="collapsed")
    filter_price_max = col_price2.number_input("🪙 最大", min_value=0, max_value=max_price_val, value=max_price_val, key="price_max", label_visibility="collapsed")
        
    # 2. 購入者数
    st.sidebar.markdown("##### 🛒 購入者数")
    col_buy1, _, col_buy2 = st.sidebar.columns([4.5, 1, 4.5], gap="small")
    filter_buy_min = col_buy1.number_input("🛒 最小", min_value=0, max_value=max_buy_val, value=0, key="buy_min", label_visibility="collapsed")
    filter_buy_max = col_buy2.number_input("🛒 最大", min_value=0, max_value=max_buy_val, value=max_buy_val, key="buy_max", label_visibility="collapsed")
    
    # 3. 直近販売日３ (日付範囲指定)
    st.sidebar.markdown("##### 📅 直近販売日３")
    col_sales3_1, _, col_sales3_2 = st.sidebar.columns([4.5, 1, 4.5], gap="small")
    filter_sales3_min = col_sales3_1.date_input("📅 開始", value=datetime(2020, 1, 1).date(), max_value=datetime.now().date(), key="sales3_min", label_visibility="collapsed")
    filter_sales3_max = col_sales3_2.date_input("📅 終了", value=datetime.now().date(), max_value=datetime.now().date(), key="sales3_max", label_visibility="collapsed")
        
    # 4. ユーザーの総評価数
    st.sidebar.markdown("##### 💬 ユーザーの総評価数")
    col_rev1, _, col_rev2 = st.sidebar.columns([4.5, 1, 4.5], gap="small")
    filter_rev_min = col_rev1.number_input("💬 最小", min_value=0, max_value=max_rev_val, value=0, key="rev_min", label_visibility="collapsed")
    filter_rev_max = col_rev2.number_input("💬 最大", min_value=0, max_value=max_rev_val, value=max_rev_val, key="rev_max", label_visibility="collapsed")
    
    # 5. 直近1ヶ月の総評価数
    st.sidebar.markdown("##### 📅 直近1ヶ月の総評価数")
    filter_recent = st.sidebar.selectbox("📅 直近1ヶ月の総評価数", ("すべて", "1件以上", "5件以上", "10件以上", "20件以上"), label_visibility="collapsed")

    # 数値ベースのフィルター適用
    query_df = df_filter[
        (df_filter["_price_num"] >= filter_price_min) & (df_filter["_price_num"] <= filter_price_max) &
        (df_filter["_buy_num"] >= filter_buy_min) & (df_filter["_buy_num"] <= filter_buy_max) &
        (df_filter["_rev_num"] >= filter_rev_min) & (df_filter["_rev_num"] <= filter_rev_max)
    ]
    
    # 直近販売日3の日付範囲判定ロジック
    def check_sales3_date_range(date_str):
        if date_str in ["-", "3ヶ月以上前"]:
            return False
        try:
            target_dt = datetime.strptime(date_str, "%Y.%m.%d").date()
            return filter_sales3_min <= target_dt <= filter_sales3_max
        except:
            return False
            
    query_df = query_df[query_df["直近販売日3"].apply(check_sales3_date_range)]
    
    if filter_recent == "1件以上": query_df = query_df[query_df["_recent_num"] >= 1]
    elif filter_recent == "5件以上": query_df = query_df[query_df["_recent_num"] >= 5]
    elif filter_recent == "10件以上": query_df = query_df[query_df["_recent_num"] >= 10]
    elif filter_recent == "20件以上": query_df = query_df[(query_df["_recent_num"] >= 20) | (query_df["直近1ヶ月の評価数"] == "20件以上")]

    final_df = query_df.drop(columns=["_price_num", "_buy_num", "_rev_num", "_recent_num"])
    
    target_columns = [
        "No.", "作家名", "商品名", "価格(円)", "商品URL", 
        "お気に入り数", "購入者数", "直近販売日1", "直近販売日2", "直近販売日3", 
        "総評価数", "直近1ヶ月の評価数", "一番初めの評価日"
    ]
    final_df = final_df.reindex(columns=target_columns)
    
    if not final_df.empty: 
        final_df["No."] = range(1, len(final_df) + 1)
        
    final_df = final_df.rename(columns={
        "総評価数": "ユーザーの総評価数",
        "直近1ヶ月の評価数": "直近1ヶ月の総評価数"
    })
    
    st.success(f"📊 条件に一致した商品: {len(final_df)} 件 / 全件中")
    excel_data = convert_df_to_excel(final_df)
    
    st.download_button(
        label="📥 絞り込んだデータをExcelでダウンロード",
        data=excel_data,
        file_name=f"Creemaリサーチ_絞り込み済_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    st.subheader("👀 絞り込み結果のプレビュー")
    st.dataframe(
        final_df, 
        use_container_width=True, 
        height=400, 
        hide_index=True,
        column_config={
            "商品名": st.column_config.TextColumn("商品名", width=250), 
            "商品URL": st.column_config.LinkColumn("商品URL", display_text="ページを開く 🔗")
        }
    )

    # =============================================
    #   📊 🎯 100件以上の場合のみ使える「売れやすさ計算」機能
    # =============================================
    total_raw_count = len(st.session_state.raw_data)
    
    st.markdown("---")
    st.subheader("📊 独立マーケット分析（売れやすさ計算）")
    
    if total_raw_count < 100:
        st.warning(f"⚠️ この機能は100件以上のデータを取得した際にご利用いただけます。（現在: {total_raw_count}件）")
    else:
        st.info("💡 100件以上のデータが確認できました。精緻な売れやすさ分析が可能です。")
        
        if st.button("📊 売れやすさ指標を計算する", type="secondary"):
            st.session_state.show_calculator = True
            
        if st.session_state.get("show_calculator", False):
            # Creemaの総検索結果件数を入力してもらう
            total_market_items = st.number_input(
                "🔍 Creema上のこのキーワード/カテゴリーの「総検索結果件数」を入力してください（例: 170918）",
                min_value=100, max_value=5000000, value=170000, step=1000
            )
            
            # 条件合致件数の計算（総合レビュー1000以下、かつ直近販売日3が1ヶ月以内）
            calc_one_month_ago = datetime.now() - timedelta(days=30)
            target_match_count = 0
            
            for item in st.session_state.raw_data:
                # ユーザーの総評価数
                try: r_num = int(re.sub(r"\D", "", item["総評価数"]))
                except: r_num = 0
                
                # 直近販売日3
                s3_str = item["直近販売日3"]
                is_s3_recent = False
                if s3_str not in ["-", "3ヶ月以上前", "取得失敗"]:
                    try:
                        s3_dt = datetime.strptime(s3_str, "%Y.%m.%d")
                        if s3_dt >= calc_one_month_ago:
                            is_s3_recent = True
                    except: pass
                
                if r_num <= 1000 and is_s3_recent:
                    target_match_count += 1
            
            # 基本アクティブ比率 (A)
            base_active_rate = target_match_count / total_raw_count
            
            # 市場規模ボーナス倍率 (B) - 17万件など巨大市場の上位100件であることの価値を加味
            # 対数を用いて、100件が市場全体に占める「狭き門度（エリート度）」を補正値化
            market_elite_index = total_market_items / total_raw_count
            log_bonus = float(np.log10(market_elite_index)) if market_elite_index > 1 else 1.0
            
            # スコア算出 (0 - 100点調整)
            raw_score = (base_active_rate * 60) + (log_bonus * 12)
            final_score = min(max(int(raw_score), 5), 100)
            
            # 判定ロジック
            if final_score >= 70:
                judge_title = "🔥 激アツ（超おすすめ市場）"
                judge_desc = "上位層が活発に動いているにも関わらず、レビュー1000件以下の「これからの作家」がゴリゴリ売上を上げています。参入価値が極めて高いブルーオーシャンです。"
                color = "#D4EDDA"
            elif final_score >= 45:
                judge_title = "✨ 狙い目（十分にチャンスあり）"
                judge_desc = "適度に回転しており、新着や工夫次第で上位に食い込める余地が大きいです。強すぎる絶対王者が少なく、戦いやすい市場です。"
                color = "#CCE5FF"
            elif final_score >= 25:
                judge_title = "⚖️ レッドオーシャン（強者独占型）"
                judge_desc = "上位100件の顔ぶれが固定化されているか、レビュー数数千件の超大手が市場を牛耳っています。凡人が同じ戦い方をしても埋もれるため、ひねり（コンセプト違い）が必要です。"
                color = "#FFF3CD"
            else:
                judge_title = "❄️ お休み市場（需要低迷）"
                judge_desc = "人気順上位であるにも関わらず、直近1ヶ月以内の動きが鈍いです。市場全体の動きが止まっている可能性があるため、別のキーワードを攻めることをお勧めします。"
                color = "#F8D7DA"
                
            # 結果表示
            st.markdown(f"""
                <div class="metric-card" style="background-color: {color}; border-left-color: #111111;">
                    <h3 style="margin-top:0;">分析結果スコア: <span style="font-size:36px; font-weight:bold;">{final_score}</span> / 100点</h3>
                    <h4>判定：{judge_title}</h4>
                    <p style="font-size:14px; margin-bottom:5px;"><b>🔍 算出内訳:</b></p>
                    <ul>
                        <li>調査した上位 {total_raw_count} 件中、条件合致（評価1000以下＆1ヶ月以内販売）商品: <b>{target_match_count} 件</b></li>
                        <li>市場エリート度（総件数 {total_market_items} 件に対する希少価値補正）: <b>ベーススコアに良好に加算済</b></li>
                    </ul>
                    <p style="font-size:14.5px; line-height:1.6; background:rgba(255,255,255,0.5); padding:10px; border-radius:4px;">{judge_desc}</p>
                </div>
            """, unsafe_allow_html=True)
