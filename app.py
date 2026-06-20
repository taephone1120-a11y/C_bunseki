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
st.set_page_config(page_title="Creema市場リサーチツール", page_icon="💎", layout="wide")

# 🎨 【CSS再調整】横線の上下に心地よいスペース（余白）を確保
st.markdown("""
    <style>
    /* 画面最上部に自然な余白を確保 */
    .block-container {
        padding-top: 2.5rem !important;
        padding-bottom: 2rem !important;
    }
    
    /* 文字サイズを標準的な「14px」に設定 */
    html, body, [data-testid="stMarkdownContainer"] p, .stMarkdown p {
        font-size: 14px !important;
        font-family: "Meiryo", "Helvetica Neue", Arial, sans-serif;
        line-height: 1.5 !important;
    }
    
    /* 💎 タイトルの表示 */
    h1 {
        font-size: 28px !important;
        font-weight: 700 !important;
        color: #111111 !important;
        margin-top: 0px !important;
        margin-bottom: 0px !important;
        padding-top: 0px !important;
        padding-bottom: 0px !important;
        display: block !important;
    }
    
    /* サイドバーのフィルター項目も見やすい大きさに調整 */
    div[data-testid="stSidebarUserContent"] {
        padding-top: 1rem !important;
    }
    div[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h5 {
        font-size: 13.5px !important;
        margin-top: 12px !important;
        margin-bottom: 5px !important;
        color: #111111 !important;
        font-weight: 600 !important;
    }
    
    /* 各要素の間の自然な間隔 */
    div[data-testid="element-container"] {
        margin-bottom: 0.5rem !important;
    }
    
    /* 入力欄（ボックス）の高さをしっかり確保 */
    .stTextInput input, .stNumberInput input, .stDateInput input, div[data-testid="stSelectbox"] div {
        padding: 6px 10px !important;
        min-height: 36px !important;
        height: 36px !important;
        font-size: 13.5px !important;
    }
    
    /* 入力欄外側の無駄な余白の最適化 */
    div[data-testid="stNumberInput"], div[data-testid="stDateInput"] {
        margin-bottom: 8px !important;
    }
    </style>
""", unsafe_allow_html=True)

# 💎 タイトルを表示
st.title("💎 Creema市場リサーチツール")

# 📍 【余白調整】marginの数値を変更して、線の下側（結果表示との間）に適切なスペースを空けました
st.markdown('<hr style="border: none; border-top: 1px solid #e6e6e6; margin-top: 15px; margin-bottom: 25px; padding: 0;">', unsafe_allow_html=True)

# =============================================
#   サイドバー：設定エリア
# =============================================
st.sidebar.header("⚙️ 取得条件設定")

mode = st.sidebar.radio(
    "収集モードを選択してください",
    ("キーワード検索", "一覧URL直貼り")
)

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
#   📲 LINE公式アカウントへ通知を送る関数
# =============================================
def send_line_notification(keyword_or_url, item_count):
    LINE_ACCESS_TOKEN = "SsJj64qF912H/fusrwNgsiMS6bgJqv5C9i5Rx1HlHAmux8AmFlC7Q9Pnx5pbQD/4LXbi2ftiFf1zalCCDcGQAcXBxfakpnkBPLZkKzn5G2gbuQc2vkcn2GbCJ2Yf1HmfEWQoo8KbqqJn4/tsoPr4TwdB04t89/1O/w1cDnyilFU="
    LINE_USER_ID = "Ub5228833332f8fd37bbd3d9072853f2c"
    
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }
    
    message_text = (
        f"💎 【Creemaツール】利用通知\n\n"
        f"今、誰かがリサーチを開始したよ！\n"
        f"---------------------\n"
        f"▼ 検索内容:\n{keyword_or_url}\n\n"
        f"▼ 解析上限: {item_count} 件"
    )
    
    payload = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": message_text}]}
    try:
        requests.post(url, headers=headers, json=payload, timeout=5)
    except Exception:
        pass

# =============================================
#   単一商品を解析するコアロジック
# =============================================
def fetch_single_item(item_data, headers, one_month_ago):
    try:
        link = item_data["link"]
        creator = item_data["creator"]
        title = item_data["title"]
        price = item_data["price"]

        purchase_count = "記入なし"
        favorite = "取得失敗"
        review = "取得失敗"
        recent_review_display = "0件"  
        first_review_date = "取得失敗" 
        last_page_url = None
        last_voices = []
        
        detail_res = requests.get(link, headers=headers, timeout=10)
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
                
                rating_res = requests.get(base_rating_url, headers=headers, timeout=10)
                if rating_res.status_code == 200:
                    rating_soup = BeautifulSoup(rating_res.content, "html.parser")
                    voices = rating_soup.select(".p-creator-rating-rating__voice")
                    last_voices = voices 
                    
                    recent_count = 0
                    total_on_page = len(voices)
                    
                    for voice in voices:
                        date_tag = voice.select_one(".p-creator-rating-rating__date")
                        if date_tag:
                            date_text = date_tag.text.strip()
                            date_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", date_text)
                            if date_match:
                                date_str = date_match.group(1)
                                review_date = datetime.strptime(date_str, "%Y.%m.%d")
                                if review_date >= one_month_ago:
                                    recent_count += 1
                    
                    if recent_count >= 20 and total_on_page >= 20:
                        recent_review_display = "20件以上"
                    else:
                        recent_review_display = f"{recent_count}件"

                    all_links = rating_soup.find_all("a", href=True)
                    page_data = []
                    
                    for a_tag in all_links:
                        href = a_tag["href"]
                        p_match = re.search(r"page=(\d+)", href) or re.search(r"/rating/sale/(\d+)", href)
                        if p_match:
                            p_num = int(p_match.group(1))
                            full_url = href if href.startswith("http") else "https://www.creema.jp" + href
                            page_data.append((p_num, full_url))
                    
                    if page_data:
                        _, last_page_url = max(page_data, key=lambda x: x[0])

                if last_page_url:
                    last_page_res = requests.get(last_page_url, headers=headers, timeout=10)
                    if last_page_res.status_code == 200:
                        rating_soup = BeautifulSoup(last_page_res.content, "html.parser")
                        last_voices = rating_soup.select(".p-creator-rating-rating__voice")
                
                if last_voices:
                    oldest_date = None
                    for voice in last_voices:
                        date_tag = voice.select_one(".p-creator-rating-rating__date")
                        if date_tag:
                            date_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", date_tag.text)
                            if date_match:
                                current_date = datetime.strptime(date_match.group(1), "%Y.%m.%d")
                                if oldest_date is None or current_date < oldest_date:
                                        oldest_date = current_date
                    
                    if oldest_date:
                        first_review_date = oldest_date.strftime("%Y.%m.%d")

        return {
            "作家名": creator,
            "商品名": title,
            "価格(円)": price,
            "商品URL": link,
            "お気に入り数": favorite,
            "購入者数": purchase_count,
            "総評価数": review,
            "直近1ヶ月の評価数": recent_review_display,
            "一番初めの評価日": first_review_date
        }
    except Exception:
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
    
    all_item_elements_data = []
    current_url = start_url
    page_count = 1
    
    page_status = st.empty()
    
    while current_url and len(all_item_elements_data) < max_num:
        page_status.info(f" ページ巡回中... 現在 {page_count} ページ目をスキャンしています (収集済リンク: {len(all_item_elements_data)}件)")
        try:
            response = requests.get(current_url, headers=headers, timeout=10)
            if response.status_code != 200:
                break
            soup = BeautifulSoup(response.content, "html.parser")
            
            items = soup.select("article.c-item-article")
            if not items:
                break
                
            for item in items:
                if len(all_item_elements_data) >= max_num:
                    break
                    
                title_tag = item.select_one('.c-item-article__name a[href*="/item/"]')
                if not title_tag:
                    continue
                    
                title = title_tag.text.strip()
                if not title and title_tag.find("img"):
                    title = title_tag.find("img")["alt"].strip()
                    
                link = "https://www.creema.jp" + title_tag["href"]
                
                desc_tag = item.select_one(".c-item-article__desc")
                creator = "取得失敗"
                price = 0
                if desc_tag:
                    desc_text = desc_tag.text.strip()
                    if "/" in desc_text:
                        parts = desc_text.split("/")
                        price = int(re.sub(r"\D", "", parts[0])) if parts[0] else 0
                        creator = parts[1].strip()
                
                all_item_elements_data.append({
                    "link": link,
                    "creator": creator,
                    "title": title,
                    "price": price
                })
            
            next_tag = soup.select_one("a.c-pagination__next")
            if next_tag and "href" in next_tag.attrs:
                next_href = next_tag["href"]
                current_url = next_href if next_href.startswith("http") else "https://www.creema.jp" + next_href
                page_count += 1
                time.sleep(1)
            else:
                current_url = None
                
        except Exception as e:
            st.error(f"ページ巡回中にエラーが発生しました: {e}")
            break
            
    page_status.empty()
    total_found = len(all_item_elements_data)
    
    if total_found == 0:
        st.warning("商品が見つかりませんでした。")
        return None
        
    status_text = st.empty()
    status_text.info(f"🚀 合計 {total_found}件 の商品リンクを獲得！ 5件ずつ並行で詳細リサーチを行っています...")
    progress_bar = st.progress(0)
    
    scraped_data = []
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_item = {executor.submit(fetch_single_item, item_data, headers, one_month_ago): i for i, item_data in enumerate(all_item_elements_data)}
        
        for current_idx, future in enumerate(as_completed(future_to_item), 1):
            result = future.result()
            if result:
                scraped_data.append(result)
            
            progress_bar.progress(current_idx / total_found)
            status_text.text(f"⏳ 大規模解析中... 完了: {current_idx} / {total_found} 件")
            
    progress_bar.empty()
    status_text.empty()
    
    if scraped_data:
        for i, item in enumerate(scraped_data, 1):
            item["No."] = i
        columns_order = ["No.", "作家名", "商品名", "価格(円)", "商品URL", "お気に入り数", "購入者数", "総評価数", "直近1ヶ月の評価数", "一番初めの評価日"]
        return [ {k: item[k] for k in columns_order if k in item} for item in scraped_data ]
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
        
        thin_border = Border(
            left=Side(style='thin', color='D9D9D9'), right=Side(style='thin', color='D9D9D9'),
            top=Side(style='thin', color='D9D9D9'), bottom=Side(style='thin', color='D9D9D9')
        )
        
        for row in worksheet.iter_rows(min_row=1, max_row=len(df)+1):
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
                    elif cell.column in [6, 7, 8, 9, 10]: 
                        cell.alignment = Alignment(horizontal="center", vertical="center")
                    else: 
                        cell.alignment = Alignment(horizontal="left", vertical="center")
                        
        for col in worksheet.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = col[0].column_letter
            worksheet.column_dimensions[col_letter].width = min(max(max_len + 3, 10), 50)
            
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
        
        start_time = time.time()
        data = scrape_creema_fast(target_url, max_items)
        if data:
            elapsed_time = time.time() - start_time
            st.toast(f"🎉 取得完了！ 処理時間: {elapsed_time:.1f}秒", icon="✅")
            st.session_state.raw_data = data

if st.session_state.raw_data:
    df_orig = pd.DataFrame(st.session_state.raw_data)
    df_filter = df_orig.copy()
    
    df_filter["_price_num"] = pd.to_numeric(df_filter["価格(円)"], errors='coerce').fillna(0).astype(int)
    df_filter["_fav_num"] = pd.to_numeric(df_filter["お気に入り数"].str.replace(r"\D", "", regex=True), errors='coerce').fillna(0).astype(int)
    df_filter["_buy_num"] = pd.to_numeric(df_filter["購入者数"].str.replace(r"\D", "", regex=True), errors='coerce').fillna(0).astype(int)
    df_filter["_rev_num"] = pd.to_numeric(df_filter["総評価数"].str.replace(r"\D", "", regex=True), errors='coerce').fillna(0).astype(int)
    df_filter["_recent_num"] = pd.to_numeric(df_filter["直近1ヶ月の評価数"].str.replace(r"\D", "", regex=True), errors='coerce').fillna(0).astype(int)
    
    max_price_val = int(df_filter["_price_num"].max())
    max_fav_val = int(df_filter["_fav_num"].max())
    max_buy_val = int(df_filter["_buy_num"].max())
    max_rev_val = int(df_filter["_rev_num"].max())

    # =============================================
    #   サイドバー：データ絞り込みフィルター
    # =============================================
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🎯 データ絞り込みフィルター")
    
    st.sidebar.markdown("##### 🪙 金額(円)")
    col_price1, col_price_mid, col_price2 = st.sidebar.columns([4.5, 1, 4.5], gap="small")
    with col_price1:
        filter_price_min = st.number_input("🪙 金額 最小", min_value=0, max_value=max_price_val, value=0, key="price_min", label_visibility="collapsed")
    with col_price_mid:
        st.markdown("<div style='text-align: center; line-height: 36px; font-size: 13px;'>〜</div>", unsafe_allow_html=True)
    with col_price2:
        filter_price_max = st.number_input("🪙 金額 最大", min_value=0, max_value=max_price_val, value=max_price_val, key="price_max", label_visibility="collapsed")
    
    st.sidebar.markdown("##### ⭐ お気に入り数")
    col_fav1, col_fav_mid, col_fav2 = st.sidebar.columns([4.5, 1, 4.5], gap="small")
    with col_fav1:
        filter_fav_min = st.number_input("⭐ お気に入り数 最小", min_value=0, max_value=max_fav_val, value=0, key="fav_min", label_visibility="collapsed")
    with col_fav_mid:
        st.markdown("<div style='text-align: center; line-height: 36px; font-size: 13px;'>〜</div>", unsafe_allow_html=True)
    with col_fav2:
        filter_fav_max = st.number_input("⭐ お気に入り数 最大", min_value=0, max_value=max_fav_val, value=max_fav_val, key="fav_max", label_visibility="collapsed")
        
    st.sidebar.markdown("##### 🛒 購入者数")
    col_buy1, col_buy_mid, col_buy2 = st.sidebar.columns([4.5, 1, 4.5], gap="small")
    with col_buy1:
        filter_buy_min = st.number_input("🛒 購入者数 最小", min_value=0, max_value=max_buy_val, value=0, key="buy_min", label_visibility="collapsed")
    with col_buy_mid:
        st.markdown("<div style='text-align: center; line-height: 36px; font-size: 13px;'>〜</div>", unsafe_allow_html=True)
    with col_buy2:
        filter_buy_max = st.number_input("🛒 購入者数 最大", min_value=0, max_value=max_buy_val, value=max_buy_val, key="buy_max", label_visibility="collapsed")
        
    st.sidebar.markdown("##### 💬 総評価数")
    col_rev1, col_rev_mid, col_rev2 = st.sidebar.columns([4.5, 1, 4.5], gap="small")
    with col_rev1:
        filter_rev_min = st.number_input("💬 総評価数 最小", min_value=0, max_value=max_rev_val, value=0, key="rev_min", label_visibility="collapsed")
    with col_rev_mid:
        st.markdown("<div style='text-align: center; line-height: 36px; font-size: 13px;'>〜</div>", unsafe_allow_html=True)
    with col_rev2:
        filter_rev_max = st.number_input("💬 総評価数 最大", min_value=0, max_value=max_rev_val, value=max_rev_val, key="rev_max", label_visibility="collapsed")
    
    st.sidebar.markdown("##### 📅 直近1ヶ月の評価数")
    filter_recent = st.sidebar.selectbox(
        "📅 直近1ヶ月の評価数",
        ("すべて", "1件以上", "5件以上", "10件以上", "20件以上"),
        label_visibility="collapsed"
    )
    
    st.sidebar.markdown("##### ⏱️ 一番初めの評価日")
    col_date1, col_date_mid, col_date2 = st.sidebar.columns([4.5, 1, 4.5], gap="small")
    with col_date1:
        filter_date_min = st.date_input("⏱️ 一番初めの評価日 開始日", value=datetime(2010, 1, 1).date(), max_value=datetime.now().date(), key="date_min", label_visibility="collapsed")
    with col_date_mid:
        st.markdown("<div style='text-align: center; line-height: 36px; font-size: 13px;'>〜</div>", unsafe_allow_html=True)
    with col_date2:
        filter_date_max = st.date_input("⏱️ 一番初めの評価日 終了日", value=datetime.now().date(), max_value=datetime.now().date(), key="date_max", label_visibility="collapsed")

    # =============================================
    #   フィルター条件の適用
    # =============================================
    query_df = df_filter[
        (df_filter["_price_num"] >= filter_price_min) & (df_filter["_price_num"] <= filter_price_max) &
        (df_filter["_fav_num"] >= filter_fav_min) & (df_filter["_fav_num"] <= filter_fav_max) &
        (df_filter["_buy_num"] >= filter_buy_min) & (df_filter["_buy_num"] <= filter_buy_max) &
        (df_filter["_rev_num"] >= filter_rev_min) & (df_filter["_rev_num"] <= filter_rev_max)
    ]
    
    if filter_recent == "1件以上":
        query_df = query_df[query_df["_recent_num"] >= 1]
    elif filter_recent == "5件以上":
        query_df = query_df[query_df["_recent_num"] >= 5]
    elif filter_recent == "10件以上":
        query_df = query_df[query_df["_recent_num"] >= 10]
    elif filter_recent == "20件以上":
        query_df = query_df[(query_df["_recent_num"] >= 20) | (query_df["直近1ヶ月の評価数"] == "20件以上")]

    def check_date_range(date_str):
        try:
            if date_str == "取得失敗":
                return False
            d = datetime.strptime(date_str, "%Y.%m.%d").date()
            return filter_date_min <= d <= filter_date_max
        except:
            return False
            
    query_df = query_df[query_df["一番初めの評価日"].apply(check_date_range)]

    final_df = query_df.drop(columns=["_price_num", "_fav_num", "_buy_num", "_rev_num", "_recent_num"])
    if not final_df.empty:
        final_df["No."] = range(1, len(final_df) + 1)
    
    # =============================================
    #   結果表示エリア
    # =============================================
    st.success(f"📊 条件に一致した商品: {len(final_df)} 件 / 全件中")
    
    download_filename = f"Creemaリサーチ_絞り込み済_{datetime.now().strftime('%Y%m%d')}.xlsx"
    excel_data = convert_df_to_excel(final_df)
    
    st.download_button(
        label="📥 絞り込んだデータをExcelでダウンロード",
        data=excel_data,
        file_name=download_filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    st.subheader("👀 絞り込み結果のプレビュー")
    st.dataframe(
        final_df, 
        use_container_width=True,
        height=800,
        column_config={
            "商品名": st.column_config.TextColumn("商品名", width=250),
            "商品URL": st.column_config.LinkColumn("商品URL", display_text="ページを開く 🔗")
        }
    )
