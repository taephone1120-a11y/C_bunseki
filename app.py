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
    # 💡 【完全内蔵】1件詳細解析用パーツ
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
            purchase_date = "-"  # 👈 【追加】購入日を格納する変数を初期化
            
            try:
                detail_res = requests.get(link, headers=headers, timeout=10)
                if detail_res.status_code == 200:
                    detail_soup = BeautifulSoup(detail_res.content, "html.parser")
                    
                    # 1. 作品紹介文
                    try:
                        desc_element = detail_soup.select_one(".p-item-detail-description, .js-item-description, .p-item-detail__description")
                        if desc_element: 
                            description_text = desc_element.text.strip()
                    except: pass

                    # ----------------------------------------------------
                    # 🎯 【追加】特定のタイトルの下から日付を抽出する処理
                    # ----------------------------------------------------
                    try:
                        target_title = "ここに探したいタイトルの文字列"  # 👈 実際に探したい文字列（例: "購入日時" など）に書き換えてください
                        
                        if target_title in description_text:
                            # タイトル以降の文字列を切り取る
                            after_title_text = description_text.split(target_title, 1)[1]
                            
                            # 最初に出てくる日付（例: 2026.06.25 や 2026/06/25 など）を正規表現で探す
                            date_match = re.search(r"(\d{4}[./-]\d{2}[./-]\d{2})", after_title_text)
                            if date_match:
                                purchase_date = date_match.group(1)  # 見つかった日付をセット
                    except:
                        purchase_date = "解析失敗"
                    # ----------------------------------------------------

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

# 5. 評価ページの解析（原因究明デバッグ版）
                    if rating_link_tag:
                        try:
                            base_rating_url = "https://www.creema.jp" + rating_link_tag["href"]
                            if "?" in base_rating_url:
                                base_rating_url = base_rating_url.split("?")[0]
                            
                            local_three_months_ago = datetime.now() - timedelta(days=90)
                            
                            all_matched_dates = []
                            current_page = 1
                            current_url = base_rating_url
                            clean_target = " ".join(title.strip().split())
                            
                            # 💡 画面に変数の初期状態を出力
                            st.write(f"🔍【デバッグ】解析開始: {title}")
                            st.write(f"🔍【デバッグ】ターゲットURL: {base_rating_url}")
                            st.write(f"🔍【デバッグ】3ヶ月前の基準日: {local_three_months_ago.strftime('%Y.%m.%d')}")
                            
                            while current_url and current_page <= 10:  
                                try:
                                    res = requests.get(current_url, headers=headers, timeout=8)
                                    if res.status_code != 200: 
                                        st.write(f"⚠️【デバッグ】ページ {current_page} でステータスエラー: {res.status_code}")
                                        break
                                    
                                    soup = BeautifulSoup(res.content, "html.parser")
                                    blocks = soup.select(".p-creator-rating-rating__content")
                                    if not blocks: 
                                        st.write(f"⚠️【デバッグ】ページ {current_page} にレビューブロックがありません")
                                        break
                                    
                                    page_hits = 0
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
                                                        review_date = datetime.strptime(date_match.group(1), "%Y.%m.%d")
                                                        if review_date >= local_three_months_ago:
                                                            all_matched_dates.append(review_date)
                                                            page_hits += 1
                                                            
                                    st.write(f"📄【デバッグ】ページ {current_page} をスキャン終了。このページでの一致件数: {page_hits}件")
                                    
                                    if len(all_matched_dates) >= 3:
                                        st.write(f"🚨【デバッグ】1ページ目で3件以上見つかったので終了します（合計: {len(all_matched_dates)}件）")
                                        break
                                    
                                    # ブレーキ機能のログ
                                    all_page_dates = []
                                    for v_tag in soup.select(".p-creator-rating-rating__voice"):
                                        d_tag = v_tag.select_one(".p-creator-rating-rating__date")
                                        if d_tag:
                                            d_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", d_tag.text)
                                            if d_match: all_page_dates.append(datetime.strptime(d_match.group(1), "%Y.%m.%d"))
                                    
                                    if all_page_dates and max(all_page_dates) < local_three_months_ago: 
                                        st.write(f"🛑【デバッグ】ページ内の最新レビュー({max(all_page_dates).strftime('%Y.%m.%d')})が3ヶ月以上前なので、ブレーキをかけてループを抜けます")
                                        break
                                    
                                    current_page += 1
                                    current_url = f"{base_rating_url}?page={current_page}"
                                    time.sleep(0.1)
                                except Exception as e:
                                    st.write(f"❌【デバッグ】ループ内で例外発生: {e}")
                                    break
                            
                            all_matched_dates.sort(reverse=True)
                            sorted_dates = [d.strftime("%Y.%m.%d") for d in all_matched_dates[:3]]
                            
                            st.write(f"📦【デバッグ】ソート後のデータトップ3: {sorted_dates}")
                            
                            final_sales_list = ["3ヶ月以上前", "3ヶ月以上前", "3ヶ月以上前"]
                            total_found = len(sorted_dates)
                            
                            if total_found == 0 and current_page > 10:
                                final_sales_list = ["取得失敗", "取得失敗", "取得失敗"]
                            else:
                                if total_found >= 1: final_sales_list[0] = sorted_dates[0]
                                if total_found >= 2: final_sales_list[1] = sorted_dates[1]
                                if total_found >= 3: final_sales_list[2] = sorted_dates[2]
                            
                            st.write(f"📢【デバッグ】最終的に recent_sales に代入する直前の値: {final_sales_list}")
                            recent_sales = final_sales_list
                                        
                        except Exception as e: 
                            st.write(f"❌【デバッグ】全体でエラー発生: {e}")

# 6. 直近1ヶ月の評価数
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

                        try:
                            all_links = rating_soup.find_all("a", href=True)
                            page_data = []
                            for a_tag in all_links:
                                href = a_tag["href"]
                                p_match = re.search(r"page=(\d+)", href) or re.search(r"/rating/sale/(\d+)", href)
                                if p_match: page_data.append((int(p_match.group(1)), href if href.startswith("http") else "https://www.creema.jp" + href))
                            if page_data: _, last_page_url = max(page_data, key=lambda x: x[0])
                        except: pass

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
            except:
                description_text = "通信エラー"

            return {
                "No.": 0, "作家名": creator, "商品名": title, "価格(円)": price, "商品URL": link,
                "お気に入り数": favorite, "購入者数": purchase_count,  
                "直近販売日1": recent_sales[0], "直近販売日2": recent_sales[1], "直近販売日3": recent_sales[2],
                "総評価数": review, "直近1ヶ月の評価数": recent_review_display, "一番初めの評価日": first_review_date,
                "購入日": purchase_date,  # 👈 【追加】出力されるデータに購入日を含める
                "作品紹介文": description_text 
            }
        except:
            return None

    # ----------------------------------------------------
    #  メインロジックの開始（関数内部）
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
#    🚀 ボタン連動・実行処理エリア
# =============================================
# 💡 重複していた古い処理エリアは削除し、
#    セッション管理を行う以下の正しい処理一本に統合しました。

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
        
        # リサーチ関数を実行（スピナー表示を伴う）
        with st.spinner("🔄 Creemaのデータを解析中..."):
            res_dict = scrape_creema_fast(target_url, max_items)
            
        if res_dict:
            st.session_state.raw_data = res_dict["items"]
            st.session_state.market_total = res_dict["market_total"]
            st.success(f"🎉 リサーチ完了！ 全 {len(res_dict['items'])} 件のデータを取得しました。(市場総件数: {res_dict['market_total']:,}件)")
            st.toast(f"🎉 取得完了しました！（全体総件数: {res_dict['market_total']:,}件）", icon="✅")
        else:
            st.error("❌ データが取得できませんでした。URLやキーワードを再度確認してください。")


# =============================================
#    Excelダウンロード用バイナリ生成
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
#     📊 データフィルタリングと画面表示
# =============================================
if st.session_state.raw_data and len(st.session_state.raw_data) > 0:
    import pandas as pd
    import numpy as np
    import re
    
    df_orig = pd.DataFrame(st.session_state.raw_data)
    
    # =============================================
    # 🔄 [自動修復] もし英語のキー名でデータが来ていたら、正しい日本語列名に変換
    # =============================================
    rename_mapping = {
        "artist_name": "作家名", "creator": "作家名", "creator_name": "作家名", "writer": "作家名",
        "title": "商品名", "item_name": "商品名", "name": "商品名",
        "price": "価格(円)", "price_yen": "価格(円)",
        "url": "商品URL", "item_url": "商品URL",
        "favorite": "お気に入り数", "like_count": "お気に入り数", "fav": "お気に入り数", "likes": "お気に入り数",
        "buy_count": "購入者数", "sales_count": "購入者数", "buy_num": "購入者数",
        "sales_date1": "直近販売日1", "sales_date2": "直近販売日2", "sales_date3": "直近販売日3",
        "date1": "直近販売日1", "date2": "直近販売日2", "date3": "直近販売日3",
        "total_review": "総評価数", "review_count": "総評価数", "rating_count": "総評価数", "reviews": "総評価数",
        "recent_review": "直近1ヶ月の評価数", "recent_count": "直近1ヶ月の評価数", "recent_num": "直近1ヶ月の評価数",
        "first_review": "一番初めの評価日", "first_date": "一番初めの評価日",
        "description": "作品紹介文", "text": "作品紹介文", "intro": "作品紹介文"
    }
    df_orig = df_orig.rename(columns=rename_mapping)
    
    # 💡 どの名前にも引っかからなかった場合、Noneを回避するために最低限の空枠を作る
    expected_cols = [
        "作家名", "商品名", "価格(円)", "商品URL", "お気に入り数", "購入者数",
        "直近販売日1", "直近販売日2", "直近販売日3", "総評価数", "直近1ヶ月の評価数", "一番初めの評価日", "作品紹介文"
    ]
    for col in expected_cols:
        if col not in df_orig.columns:
            df_orig[col] = "-"

    df_filter = df_orig.copy()
    
    def clean_purchase_count(val):
        if pd.isna(val) or val == 0 or val == "-": return 0
        val_str = str(val).strip()
        num_match = re.search(r"(\d+)", val_str)
        return int(num_match.group(1)) if num_match else 0

    # 💡 数値データの安全クレンジング（Noneや文字列の混入を完全にガード）
    df_filter["_price_num"] = df_filter["価格(円)"].astype(str).str.replace(r"\D", "", regex=True)
    df_filter["_price_num"] = pd.to_numeric(df_filter["_price_num"], errors='coerce').fillna(0).astype(int)

    df_filter["_buy_num"] = df_filter["購入者数"].apply(clean_purchase_count)

    df_filter["_rev_num"] = df_filter["総評価数"].astype(str).str.replace(r"\D", "", regex=True)
    df_filter["_rev_num"] = pd.to_numeric(df_filter["_rev_num"], errors='coerce').fillna(0).astype(int)

    df_filter["_recent_num"] = df_filter["直近1ヶ月の評価数"].astype(str).str.replace(r"\D", "", regex=True)
    df_filter["_recent_num"] = pd.to_numeric(df_filter["_recent_num"], errors='coerce').fillna(0).astype(int)

    # 表示用に元の列の None を安全に穴埋め
    df_filter["価格(円)"] = df_filter["価格(円)"].fillna("-")
    df_filter["総評価数"] = df_filter["総評価数"].fillna("0件")
    df_filter["直近1ヶ月の評価数"] = df_filter["直近1ヶ月の評価数"].fillna("0件")
    df_filter["お気に入り数"] = df_filter["お気に入り数"].fillna(0)
    df_filter["作家名"] = df_filter["作家名"].fillna("-")
    df_filter["商品名"] = df_filter["商品名"].fillna("-")
    df_filter["商品URL"] = df_filter["商品URL"].fillna("")

    # 購入者数に応じた「直近販売日」のマスク処理
    target_sales_cols = ["直近販売日1", "直近販売日2", "直近販売日3"]
    df_filter.loc[df_filter["_buy_num"] == 0, target_sales_cols] = "-"
    df_filter.loc[df_filter["_buy_num"] == 1, ["直近販売日2", "直近販売日3"]] = "-"
    df_filter.loc[df_filter["_buy_num"] == 2, ["直近販売日3"]] = "-"

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
        if filter_sales3_min is None and filter_sales3_max is None: return True
        if date_str in ["-", "3ヶ月以上前", "取得失敗"]: return False
        try:
            target_dt = datetime.strptime(date_str, "%Y.%m.%d").date()
            return (filter_sales3_min is None or target_dt >= filter_sales3_min) and (filter_sales3_max is None or target_dt <= filter_sales3_max)
        except: return False

   # =============================================
    # 💡 [安全ガード] 列の存在チェックと代入
    # =============================================
    if "_buy_num" in query_df.columns:
        query_df["購入者数"] = query_df["_buy_num"]
    elif "購入者数" in df_filter.columns:
        # 万が一query_dfから消えていた場合は、元のdf_filterの計算結果から復元
        query_df["購入者数"] = df_filter["_buy_num"]
    else:
        # どちらにもなければ0で埋める（エラー落ちを絶対に防ぐ）
        query_df["購入者数"] = 0
    
    # 一時的な計算用列を削除
    drop_cols = [c for c in ["_price_num", "_buy_num", "_rev_num", "_recent_num"] if c in query_df.columns]
    final_df = query_df.drop(columns=drop_cols)
    
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
    if not final_df.empty:
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

        candidate_items = final_df.head(10).copy()
        st.session_state["candidate_items"] = candidate_items

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
saved_candidate_items = st.session_state.get("candidate_items", None)

if saved_candidate_items is not None and not saved_candidate_items.empty:
    candidate_items = saved_candidate_items

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
    import textwrap
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
            ■作品のタイトル: {my_product_title}
            ■作品の説明・特徴・こだわり: {my_work_description}
            ---

            # 出力内容
            1. 人気商品の紹介文分析
            2. 出品作品の魅力整理
            3. 作品紹介文の提案（3パターン）
            4. 検索対策キーワード一覧（20個以上）
            """).strip()

            st.subheader("📋 【作品紹介文用】AI用コピーテキスト")
            st.success("✨ 作品紹介文用のプロンプトが完成しました！下の枠内のテキストをすべてコピーして、ChatGPTやGeminiに貼り付けてください。")

            st.text_area("以下の文章を丸ごとコピーしてください：", value=final_desc_prompt, height=400, key="desc_prompt_area")

            import json
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
    # 💡 初期状態やデータがない時の案内メッセージ
    st.info("👋 上記の「リサーチ開始」ボタンを押すと、ここにデータの分析結果や絞り込みフィルターが表示されます。")
