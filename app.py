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
                
            time.sleep(0.1)  
            
        except:
            break
            
    all_matched_dates.sort(reverse=True)
    return [d.strftime("%Y.%m.%d") for d in all_matched_dates]

# =============================================
#   単一商品を詳細解析
# =============================================
def fetch_single_item(item_data, headers, one_month_ago, three_months_ago):
    try:
        link = item_data["link"]
        creator = item_data["creator"]
        title = item_data["title"]
        price = item_data["price"]

        purchase_count = 0  
        favorite = "取得失敗"
        review = "取得失敗"
        recent_review_display = "0件"  
        first_review_date = "取得失敗" 
        last_page_url = None
        last_voices = []
        recent_sales = ["-", "-", "-"]
        description_text = "取得失敗" 
        
        detail_res = requests.get(link, headers=headers, timeout=8)
        if detail_res.status_code == 200:
            detail_soup = BeautifulSoup(detail_res.content, "html.parser")
            
            desc_element = detail_soup.select_one(".js-item-description, .p-item-detail__description")
            if desc_element:
                description_text = desc_element.text.strip()

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
                
                required_sales_count = 0
                if isinstance(purchase_count, str):
                    buy_num_match = re.search(r"(\d+)", purchase_count)
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
            "作品紹介文": description_text 
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
    detected_market_total = 170000 
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
        
    status_text = st.empty()
    progress_bar = st.progress(0)
    scraped_data = []
    
    with ThreadPoolExecutor(max_workers=15) as executor:
        future_to_item = {executor.submit(fetch_single_item, item_data, headers, one_month_ago, three_months_ago): i for i, item_data in enumerate(all_item_elements_data)}
        for current_idx, future in enumerate(as_completed(future_to_item), 1):
            result = future.result()
            if result: scraped_data.append(result)
            progress_bar.progress(current_idx / total_found)
            status_text.text(f"⏳ 大規模解析中... 完了: {current_idx} / {total_found} 件")
            
    progress_bar.empty()
    status_text.empty()
    
    if scraped_data:
        for i, item in enumerate(scraped_data, 1): item["No."] = i
        return {"items": scraped_data, "market_total": detected_market_total}
    return None

# =============================================
#   Excelダウンロード用バイナリ生成
# =============================================
def convert_df_to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        export_df = df.drop(columns=["作品紹介文"]) if "作品紹介文" in df.columns else df
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
                    if cell.column in [1, 4]: cell.alignment = Alignment(horizontal="right", vertical="center")
                    elif cell.column in [6, 7, 8, 9, 10, 11, 12, 13]: cell.alignment = Alignment(horizontal="center", vertical="center")
                    else: cell.alignment = Alignment(horizontal="left", vertical="center")
        for col in worksheet.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            worksheet.column_dimensions[col[0].column_letter].width = min(max(max_len + 3, 10), 50)
    return output.getvalue()

# =============================================
#   📞 Gemini API 呼び出し関数
# =============================================
def generate_text_with_gemini(api_key, target_title, target_desc, my_stone, my_features):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    
    prompt = f"""
あなたはハンドメイドマーケット（Creema / minne）での作品プロモーション、およびコピーライティングの専門家です。
現在市場で実際に売れている「参考作品」のデータ（タイトル・紹介文）を分析し、その強みや売れる要素を抽出した上で、ユーザーの新作のための「作品タイトル」および「作品紹介文」を魅力的に提案してください。

---
【分析対象の参考作品（売れ筋）】
■作品タイトル: {target_title}
■作品紹介文:
{target_desc}

---
【ユーザーがこれから出品したい作品の情報】
■使用している天然石: {my_stone}
■作品の特徴・こだわり・仕様:
{my_features}
---

以下の構成で、丁寧に出力してください。

### 1. 参考作品の徹底分析結果
* **タイトルの傾向**: 参考作品がどのようなキーワードの並び順、フック（【】や記号の使い方）を用いてクリック率を上げているか分析してください。
* **紹介文の構成・アピール手法**: 読者の心をつかむストーリー構成、スペック表記、購入特典の魅せ方などを分析してください。
* **多用されているヒットキーワード**: このジャンルで刺さりやすい、参考作品内で効果的に使われているキーワードを箇条書きで5〜7個抽出してください。

### 2. あなたの作品用：作品タイトル提案（5選）
参考作品のタイトル文字数やキーワードの並べ方の法則を引き継ぎつつ、ユーザーの作品用にアレンジしたタイトルを、それぞれ異なる切り口で5パターン作成してください。（文字数はCreema/minneに適した範囲内）。

### 3. あなたの作品用：作品紹介文の提案
参考作品の「売れる構成（導入文の引き込み、作品の背景、スペック、お手入れ方法、ラッピング案内など）」の黄金比を真似しつつ、ユーザーの作品特徴を最大限に魅力化させた、そのままコピー＆ペーストで使える紹介文を作成してください。ハッシュタグ（#）の提案も含めてください。
"""
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=30)
        if res.status_code == 200:
            return res.json()["candidates"][0]["content"]["parts"][0]["text"]
        else:
            return f"❌ Gemini APIエラー (Status Code: {res.status_code})\n{res.text}"
    except Exception as e:
        return f"❌ 通信エラーが発生しました: {str(e)}"

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

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🎯 データ絞り込みフィルター")
    
    # 各種フィルター設定
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
    filter_sales3_min = col_sales3_1.date_input("📅 開始", value=datetime(2020, 1, 1).date(), max_value=datetime.now().date(), key="sales3_min", label_visibility="collapsed")
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
        if filter_sales3_min == datetime(2020, 1, 1).date() and filter_sales3_max is None: return True
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
    
    target_columns = ["No.", "作家名", "商品名", "価格(円)", "商品URL", "お気に入り数", "購入者数", "直近販売日1", "直近販売日2", "直近販売日3", "総評価数", "直近1ヶ月の評価数", "一番初めの評価日", "作品紹介文"]
    final_df = final_df.reindex(columns=target_columns)
    if not final_df.empty: final_df["No."] = range(1, len(final_df) + 1)
        
    final_df = final_df.rename(columns={"総評価数": "ユーザーの総評価数", "直近1ヶ月の評価数": "直近1ヶ月の総評価数"})
    
    st.success(f"📊 条件に一致した商品: {len(final_df)} 件 / 全件中")
    excel_data = convert_df_to_excel(final_df)
    
    st.download_button(
        label="📥 絞り込んだデータをExcelでダウンロード",
        data=excel_data,
        file_name=f"Creemaリサーチ_絞り込み済_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    st.subheader("👀 絞り込み結果のプレビュー")
    display_df = final_df.drop(columns=["作品紹介文"]) if "作品紹介文" in final_df.columns else final_df
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
            under_1000_count, active_under_1000_count, total_recent_sales_3months = 0, 0
            
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
    #   🤖 👑 Gemini作品タイトル・紹介文提案生成エリア
    # =============================================
    st.markdown("---")
    st.subheader("🤖 Gemini売れ筋アライアンス生成アシスタント")
    
    df_recommend = df_filter.copy()
    today_dt = datetime.now()
    one_month_ago_date = (today_dt - timedelta(days=30)).date()
    three_months_ago_date = (today_dt - timedelta(days=90)).date()
    
    def get_date_obj(d_str):
        if d_str in ["-", "3ヶ月以上前", "取得失敗"]: return None
        try: return datetime.strptime(d_str, "%Y.%m.%d").date()
        except: return None

    df_recommend["_date1_obj"] = df_recommend["直近販売日1"].apply(get_date_obj)
    df_recommend["_date3_obj"] = df_recommend["直近販売日3"].apply(get_date_obj)
    
    def calc_priority_rank(row):
        d1 = row["_date1_obj"]
        d3 = row["_date3_obj"]
        buy = row["_buy_num"]
        
        if d3 and d3 >= one_month_ago_date and buy <= 500: return 1
        if d3 and d3 >= one_month_ago_date and buy <= 1000: return 2
        if d1 and d1 >= one_month_ago_date and buy <= 1000: return 3
        if d1 and d1 >= three_months_ago_date and buy <= 1000: return 4
        return 99 

    df_recommend["優先ランク"] = df_recommend.apply(calc_priority_rank, axis=1)
    df_recommend = df_recommend.sort_values(by=["優先ランク", "_buy_num"], ascending=[True, True])
    
    candidate_items = df_recommend[df_recommend["優先ランク"] != 99].head(10)
    if len(candidate_items) < 10:
        backup = df_recommend[df_recommend["優先ランク"] == 99].head(10 - len(candidate_items))
        candidate_items = pd.concat([candidate_items, backup])

    if candidate_items.empty:
        st.warning("⚠️ 現在のデータの中に、分析の参考としておすすめできる商品が見つかりませんでした。絞り込み条件を緩めて再取得してください。")
    else:
        st.markdown(f"**自動ピックアップ完了:** 最適な参考商品が {len(candidate_items)} 件見つかりました。")
        
        select_options = []
        option_to_data = {}
        for idx, row in candidate_items.iterrows():
            rank_label = f"【優先{row['優先ランク']}】" if row['優先ランク'] != 99 else "【参考】"
            display_name = f"{rank_label} (購入:{row['_buy_num']}人) {row['商品名'][:30]}..."
            select_options.append(display_name)
            # 【重要】row（Series型）をPython標準の辞書（dict）に完全変換して保存
            option_to_data[display_name] = row.to_dict()

        gemini_key = st.text_input("🔑 Gemini APIキーを入力してください", type="password", help="Google AI Studioで取得したAPIキーを入力します。")
        chosen_option = st.selectbox("🎯 AI分析の参考にする商品（推奨順）", select_options, index=0)
        
        col_input1, col_input2 = st.columns(2)
        my_stone_input = col_input1.text_input("🔮 あなたの作品の天然石", value="ラピスラズリ")
        my_features_input = col_input2.text_area(
            "🛠️ 作品の特徴・こだわり",
            value="「はだかのお守り」シリーズ。天然石をワイヤーでシンプルに留め、360度美しく見せるデザイン。",
            height=100
        )
        
        generate_btn = st.button("🚀 売れ筋を分析して提案してもらう", type="primary")
        
        if generate_btn:
            if not gemini_key:
                st.error("⚠️ Gemini APIキーを入力してください。")
            elif option_to_data[chosen_option]["作品紹介文"] == "取得失敗":
                st.error("⚠️ この商品の紹介文は取得できませんでした。別の商品を選択してください。")
            else:
                selected_row = option_to_data[chosen_option]
                with st.spinner("🧙‍♂️ AIが売れ筋を分析中..."):
                    ai_result = generate_text_with_gemini(
                        api_key=gemini_key,
                        target_title=selected_row["商品名"],
                        target_desc=selected_row["作品紹介文"],
                        my_stone=my_stone_input,
                        my_features=my_features_input
                    )
                st.markdown('<div class="ai-box">', unsafe_allow_html=True)
                st.subheader("✨ Gemini分析結果")
                st.markdown(ai_result)
                st.markdown('</div>', unsafe_allow_html=True)
