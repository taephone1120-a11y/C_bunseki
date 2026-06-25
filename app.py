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
#   サイドバー：設定エリア（ここで各種変数を定義）
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
#   1件詳細解析用パーツ（独立した関数として定義）
# =============================================
def _internal_fetch_item(item_data, headers, one_month_ago, three_months_ago):
    link = item_data["link"]
    creator = item_data["creator"]
    title = item_data["title"]
    price = item_data["price"]
    
    favorite = 0
    purchase_count = 0
    review = 0
    recent_review_display = "0件"
    first_review_date = "データなし"
    purchase_date = "データなし"
    description_text = "取得失敗"
    recent_sales = ["3ヶ月以上前", "3ヶ月以上前", "3ヶ月以上前"]
    base_rating_url = None

    try:
        res = requests.get(link, headers=headers, timeout=10)
        if res.status_code != 200:
            return None
            
        soup = BeautifulSoup(res.content, "html.parser")
        
        desc_tag = soup.select_one(".p-item-detail-body__description")
        if desc_tag:
            description_text = desc_tag.text.strip()
            
        fav_tag = soup.select_one(".c-favorite-btn__count, .p-item-detail-body__action-favorite-count")
        if fav_tag:
            favorite = int(re.sub(r"\D", "", fav_tag.text)) if re.sub(r"\D", "", fav_tag.text) else 0
            
        rating_link_tag = soup.select_one('a[href*="/rating/sale"]')
        if rating_link_tag:
            review_text = rating_link_tag.text.strip()
            review = int(re.sub(r"\D", "", review_text)) if re.sub(r"\D", "", review_text) else 0
            
            try:
                base_rating_url = "https://www.creema.jp" + rating_link_tag["href"]
                if "?" in base_rating_url:
                    base_rating_url = base_rating_url.split("?")[0]
                
                all_found_dates = []
                current_page = 1
                current_url = base_rating_url
                clean_target = " ".join(title.strip().split())
                
                while current_url and current_page <= 3:  
                    try:
                        r_res = requests.get(current_url, headers=headers, timeout=10)
                        if r_res.status_code != 200: break
                            
                        r_soup = BeautifulSoup(r_res.content, "html.parser")
                        blocks = r_soup.select(".p-creator-rating-rating__content")
                        if not blocks: break
                            
                        for block in blocks:
                            title_tags = block.select(".p-creator-rating-rating__title a")
                            is_target = False
                            for t in title_tags:
                                if " ".join(t.text.strip().split()) == clean_target:
                                    is_target = True
                                    break
                            
                            if is_target:
                                voice_tag = block.select_one(".p-creator-rating-rating__voice")
                                if voice_tag:
                                    date_tag = voice_tag.select_one(".p-creator-rating-rating__date")
                                    if date_tag:
                                        date_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", date_tag.text)
                                        if date_match:
                                            date_obj = datetime.strptime(date_match.group(1), "%Y.%m.%d")
                                            all_found_dates.append(date_obj)
                                                
                        current_page += 1
                        current_url = f"{base_rating_url}?page={current_page}"
                        time.sleep(0.1)
                    except:
                        break
                
                all_found_dates.sort(reverse=True)
                final_3_dates = [d.strftime("%Y.%m.%d") for d in all_found_dates[:3]]
                
                if len(final_3_dates) >= 1: recent_sales[0] = final_3_dates[0]
                if len(final_3_dates) >= 2: recent_sales[1] = final_3_dates[1]
                if len(final_3_dates) >= 3: recent_sales[2] = final_3_dates[2]
                            
            except:
                recent_sales = ["解析失敗", "解析失敗", "解析失敗"]

        if base_rating_url:
            try:
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
                        except: 
                            pass
                    
                    recent_review_display = "20件以上" if (recent_count >= 20 and len(voices) >= 20) else f"{recent_count}件"

                    try:
                        all_links = rating_soup.find_all("a", href=True)
                        page_data = []
                        for a_tag in all_links:
                            href = a_tag["href"]
                            p_match = re.search(r"page=(\d+)", href) or re.search(r"/rating/sale/(\d+)", href)
                            if p_match: 
                                page_data.append((int(p_match.group(1)), href if href.startswith("http") else "https://www.creema.jp" + href))
                        if page_data: 
                            _, last_page_url = max(page_data, key=lambda x: x[0])
                            
                            last_page_res = requests.get(last_page_url, headers=headers, timeout=10)
                            if last_page_res.status_code == 200:
                                last_voices = BeautifulSoup(last_page_res.content, "html.parser").select(".p-creator-rating-rating__voice")
                    except: 
                        pass
                    
                    if last_voices:
                        try:
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
                        except: 
                            first_review_date = "解析失敗"
            except:
                pass

        return {
            "No.": 0, "作家名": creator, "商品名": title, "価格(円)": price, "商品URL": link,
            "お気に入り数": favorite, "購入者数": purchase_count,  
            "直近販売日1": recent_sales[0],
            "直近販売日2": recent_sales[1],
            "直近販売日3": recent_sales[2],
            "総評価数": review, "直近1ヶ月の評価数": recent_review_display, "一番初めの評価日": first_review_date,
            "購入日": purchase_date,  
            "作品紹介文": description_text 
        }

    except Exception as e:
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
        
    # 🌟 ステップ2: 詳細解析
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
            status_text.text(f"☕️【安全装置】5秒間休憩しています...")
            time.sleep(random.uniform(4.5, 5.5))
            
    progress_bar.empty()
    status_text.empty()
    
    if scraped_data:
        for i, item in enumerate(scraped_data, 1): 
            item["No."] = i
        return {"items": scraped_data, "market_total": detected_market_total}
    return None

# =============================================
#    ⚙️ アプリ実行処理エリア（セッション制御）
# =============================================
if "raw_data" not in st.session_state: st.session_state.raw_data = None
if "market_total" not in st.session_state: st.session_state.market_total = 170000
if "target_max_items" not in st.session_state: st.session_state.target_max_items = 100

if start_button:
    if mode == "一覧URL直貼り" and not target_url:
        st.error("⚠️ URLを入力してください。")
    elif mode == "キーワード検索" and not target_url:
        st.error("⚠️ キーワードを指定してください。")
    else:
        cond_text = f"キーワード: {search_keyword}" if mode == "キーワード検索" else f"直貼りURL: {target_url}"
        send_line_notification(cond_text, max_items)
        st.session_state.target_max_items = max_items
        
        with st.spinner("🔄 Creemaのデータを解析中..."):
            res_dict = scrape_creema_fast(target_url, max_items)
            
        if res_dict:
            st.session_state.raw_data = res_dict["items"]
            st.session_state.market_total = res_dict["market_total"]
            st.success(f"🎉 リサーチ完了！ 全 {len(res_dict['items'])} 件のデータを取得しました。(市場総件数: {res_dict['market_total']:,}件)")
            st.toast(f"🎉 取得完了しました！（全体総件数: {res_dict['market_total']:,}件）", icon="✅")
        else:
            st.error("❌ データが取得できませんでした。URLやキーワードを再度確認してください。")

# --- 画面表示処理 ---
if st.session_state.raw_data is not None:
    df = pd.DataFrame(st.session_state.raw_data)
    
    # 🌟 エラー対策：データ型を明示的に数値に変換
    df["総評価数"] = pd.to_numeric(df["総評価数"], errors='coerce').fillna(0).astype(int)
    df["お気に入り数"] = pd.to_numeric(df["お気に入り数"], errors='coerce').fillna(0).astype(int)
    
    # 1. フィルター機能
    st.markdown('<h4 style="font-size:16px; font-weight:600; margin-top:10px; margin-bottom:10px;">📊 データを絞り込む</h4>', unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        min_rev = st.number_input("最小総評価数", min_value=0, value=0, step=10)
    with col2:
        max_rev = st.number_input("最大総評価数", min_value=0, value=99999, step=50)
    with col3:
        min_fav = st.number_input("最小お気に入り数", min_value=0, value=0, step=10)
    with col4:
        max_fav = st.number_input("最大お気に入り数", min_value=0, value=99999, step=50)
        
    filtered_df = df[
        (df["総評価数"] >= min_rev) & (df["総評価数"] <= max_rev) &
        (df["お気に入り数"] >= min_fav) & (df["お気に入り数"] <= max_fav)
    ].copy()
    
    if not filtered_df.empty:
        filtered_df["No."] = range(1, len(filtered_df) + 1)
        
    st.markdown(f"**現在の表示件数:** {len(filtered_df)} 件 / 全体 {len(df)} 件")
    
    # 2. メインデータテーブルの表示
    st.dataframe(filtered_df, use_container_width=True, hide_index=True)
    
    # 3. ダウンロード機能
    excel_data = convert_df_to_excel(filtered_df)
    
    st.download_button(
        label="📥 絞り込んだデータをExcelでダウンロード",
        data=excel_data,
        file_name=f"creema_research_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # =============================================
    #    📊 売れやすさ計算 (詳細版)
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
                    
                s1_str = item.get("直近販売日1", "-")
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


    # =================================================================
    # 🤖 作品タイトル・紹介文のプロンプト作成エリア
    # =================================================================
    if not filtered_df.empty:
        candidate_items = filtered_df.head(10) # 検索上位10選を対象に設定

        st.subheader("🙆 作品タイトル・紹介文のプロンプト作成")
        st.write("市場の人気を参考に、タイトルや紹介文を作成します。")
        st.caption("作品タイトルや紹介文の精度を上げるために、カテゴリ・素材・サイズ・使いやすさ・使用シーン・こだわりをできるだけ具体的に入力してください。")

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

        # 🛍️ ボタン1: タイトルプロンプト生成
        generate_btn = st.button("🚀 検索上位を狙うタイトルプロンプトを作成", type="primary")

        if generate_btn:
            with st.spinner("📝 AI用のプロンプトを作成中..."):
                items_summary = ""
                for display_no, (_, row) in enumerate(candidate_items.iterrows(), start=1):
                    item_name = row.get("商品名", "商品名不明")
                    buy_num = row.get("購入者数", "不明")
                    items_summary += f"・人気商品{display_no}: {item_name}（購入者数: {buy_num}人）\n"

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
                Creemaでは、雰囲気だけのおしゃれなタイトルよりも、「何の商品か」「どんな素材・特徴があるか」「どんな場面で使えるか」が分かるタイトルの方が、検索にも購入にもつながりやすいです。
                特に、人気商品には以下の傾向があります。
                ・タイトル前半に検索されやすいキーワードが入っている、商品カテゴリが一目で分かるなど。

                ---
                # 出力してほしい内容
                ## 1. 人気商品のタイトル分析
                ## 2. 出品作品の検索キーワード整理
                ## 3. 新作商品タイトル案（A. 検索上位重視 5案 / B. 購入率重視 5案 / C. バランス型 5案）
                ## 4. 一番おすすめのタイトルと理由
                ## 5. タイトル改善アドバイス
                """).strip()

                st.subheader("📋 AI用コピーテキストの作成完了")
                st.success("✨ 下の枠内のテキストをすべてコピーして、ChatGPTやGeminiのチャット欄に貼り付けてください。")
                st.text_area("以下の文章を丸ごとコピーしてください：", value=final_prompt, height=350, key="title_prompt_area")


        # ✍️ ボタン2: 作品紹介文プロンプト生成
        st.write("---")
        st.subheader("✍️ 作品紹介文（説明文）のプロンプト作成")

        my_product_title = st.text_input(
            "🏷️ 出品する作品のタイトル",
            value="",
            help="AIが紹介文を作成する際に、このタイトルとの整合性を意識して文章を作ります。",
            key="my_product_title_input"
        )

        generate_desc_btn = st.button("🚀 市場10選を分析して作品紹介文プロンプトを作成", type="primary", key="generate_desc_prompt_btn")

        if generate_desc_btn:
            with st.spinner("🕵️‍♂️ 市場10選の作品ページから、紹介文を読み込んでいます（数秒かかります）..."):
                descriptions_summary = ""
                for display_no, (_, row) in enumerate(candidate_items.iterrows(), start=1):
                    item_name = row.get("商品名", "商品名不明")
                    item_url = row.get("商品URL", None)
                    
                    if item_url and isinstance(item_url, str) and item_url.startswith("/"):
                        item_url = f"https://www.creema.jp{item_url}"

                    cleaned_desc = "（紹介文の取得に失敗しました）"
                    if item_url:
                        try:
                            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
                            response = requests.get(item_url, headers=headers, timeout=10)
                            if response.status_code == 200:
                                soup = BeautifulSoup(response.text, "html.parser")
                                desc_element = soup.find("div", class_="p-item-detail-description")
                                if desc_element:
                                    raw_text = desc_element.get_text("\n", strip=True)
                                    cleaned_desc = re.sub(r"\n{3,}", "\n\n", raw_text)
                        except Exception as e:
                            cleaned_desc = f"（通信エラーにより取得失敗: {str(e)}）"

                    descriptions_summary += f"■人気商品{display_no}: {item_name}\n【紹介文】:\n{cleaned_desc}\n\n"

                final_desc_prompt = f"あなたは、Creema・minneなどのハンドメイドマーケットで売れる商品ページを分析し、\n検索上位に表示されやすく、かつ購入につながる作品紹介文を作る専門家です。\n\n以下の【分析対象：人気商品の紹介文一覧】と【出品する作品の情報】をもとに、\nお気に入りだけで終わらず、購入につながりやすい作品紹介文を作成してください。\n\n---\n【分析対象：人気商品の紹介文一覧】\n{descriptions_summary}\n---\n\n【出品する作品の情報】\n■作品のタイトル: {my_product_title}\n■作品の説明・特徴・こだわり: {my_work_description}\n---\n\n# 出力内容\n1. 人気商品の紹介文分析\n2. 出品作品の魅力整理\n3. 作品紹介文の提案（3パターン）\n4. 検索対策キーワード一覧（20個以上）"

                st.subheader("📋 【作品紹介文用】AI用コピーテキスト")
                st.success("✨ 作品紹介文用のプロンプトが完成しました！下の枠内のテキストをすべてコピーして、ChatGPTやGeminiに貼り付けてください。")

                st.text_area("以下の文章を丸ごとコピーしてください：", value=final_desc_prompt, height=400, key="desc_prompt_area")

                js_safe_prompt = json.dumps(final_desc_prompt)
                copy_button_html = f"""
                <div style="margin-top: -10px; margin-bottom: 20px;">
                    <button id="copy-desc-btn" style="
                        background-color: #FF4B4B; color: white; border: none; padding: 8px 16px;
                        font-size: 14px; font-weight: bold; border-radius: 4px; cursor: pointer; width: 100%;
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
                    }});
                }});
                </script>
                """
                st.components.v1.html(copy_button_html, height=60)
    else:
        st.info("👋 上記の「リサーチ開始」ボタンを押すと、ここにデータの分析結果や絞り込みフィルターが表示されます。")
else:
    st.info("👋 上記の「リサーチ開始」ボタンを押すと、ここにデータの分析結果や絞り込みフィルターが表示されます。")
