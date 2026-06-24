import io
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from urllib.parse import quote
import numpy as np
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
import re

# =============================================
#  デザインとヘッダー設定
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
#   🎯 特定商品の全販売日を取得
# =============================================
def fetch_recent_sales_dates(base_rating_url, target_title, required_count, headers, three_months_ago):
    all_matched_dates = []
    current_page = 1
    current_url = base_rating_url
    max_pages_to_search = 5  

    if required_count <= 0:
        return []

    # 比較元となる商品ページのタイトルから前後の空白・改行を削り、空白を半角スペース1つに統一
    clean_target = " ".join(target_title.strip().split())

    while current_url and current_page <= max_pages_to_search:
        try:
            res = requests.get(current_url, headers=headers, timeout=8)
            if res.status_code != 200:
                break
            
            soup = BeautifulSoup(res.content, "html.parser")
            blocks = soup.select(".p-creator-rating-rating__content")
            if not blocks:
                break
            
            # ページ内の対象データを一度すべて集める
            for block in blocks:
                title_tags = block.select(".p-creator-rating-rating__title a")
                
                has_target_item = False
                for t in title_tags:
                    clean_review_title = " ".join(t.text.strip().split())
                    if clean_review_title == clean_target:
                        has_target_item = True
                        break
                
                if has_target_item:
                    # 💡 商品ブロックの中にある「別々のレビュー（voice）」を1つずつループ処理
                    voices = block.select(".p-creator-rating-rating__voice")
                    for voice in voices:
                        voice_date_tag = voice.select_one(".p-creator-rating-rating__date")
                        if voice_date_tag:
                            date_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", voice_date_tag.text)
                            if date_match:
                                date_str = date_match.group(1)
                                review_date = datetime.strptime(date_str, "%Y.%m.%d")
                                
                                if review_date >= three_months_ago:
                                    # 💡 【ここを修正！】
                                    # 「すでに同じ日付があるか」のチェックを削除しました。
                                    # これにより、別々のレビューであれば同じ日付でも正常に2回、3回と追加されます。
                                    all_matched_dates.append(review_date)
            
            # ページ内の全スキャンが終わった時点で、集まった日付を一度最新順に並び替える
            all_matched_dates.sort(reverse=True)
            
            # すでに必要な件数（required_count）が確保できていれば、次ページに進まず終了
            if len(all_matched_dates) >= required_count:
                break
                
            # ページ内の一番最近（最新）の日付が3ヶ月以上前であれば終了
            all_page_dates = []
            for date_tag in soup.select(".p-creator-rating-rating__date"):
                d_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", date_tag.text)
                if d_match:
                    all_page_dates.append(datetime.strptime(d_match.group(1), "%Y.%m.%d"))
            
            if all_page_dates:
                newest_date_on_page = max(all_page_dates)
                if newest_date_on_page < three_months_ago:
                    break

            current_page += 1
            if "?" in base_rating_url:
                current_url = f"{base_rating_url}&page={current_page}"
            else:
                current_url = f"{base_rating_url}?page={current_page}"
                
            time.sleep(0.1)
            
        except:
            break
            
    # 全ページから集まったすべての日付を、最終的に新しい順に並び替えて、必要な件数だけ切り出す
    all_matched_dates.sort(reverse=True)
    return [d.strftime("%Y.%m.%d") for d in all_matched_dates[:required_count]]
    
# =============================================
#   単一商品を詳細解析
# =============================================
def scrape_creema_fast(start_url, max_num):
    # 💡 必要なライブラリを関数内で完璧にすべて読み込み
    import time
    import random
    import re
    import requests
    from bs4 import BeautifulSoup
    from datetime import datetime, timedelta
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import streamlit as st

    # ----------------------------------------------------
    # 内部専用のデータ取得パーツ（fetch_single_itemをここに合体！）
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
                    
                    if review == "-" or not str(review).isdigit():
                        try:
                            all_text = detail_soup.get_text()
                            matches = re.findall(r"[（\(](\d+)[）\)]", all_text)
                            if matches: review = matches[0]
                        except: pass

                    # 5. 評価ページの解析
                    if rating_link_tag:
                        try:
                            base_rating_url = "https://www.creema.jp" + rating_link_tag["href"]
                            
                            # 直近販売日の取得
                            try:
                                sorted_dates = fetch_recent_sales_dates(base_rating_url, title, 3, headers, three_months_ago)
                                for idx in range(3):
                                    if idx < len(sorted_dates): recent_sales[idx] = sorted_dates[idx]
                                    else: recent_sales[idx] = "3ヶ月以上前"
                            except: pass
                            
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

                            # 最初の評価日の解析
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
            # 💡 【解決】合体した内部関数「_internal_fetch_item」を直接呼び出すので絶対エラーになりません！
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

def fetch_single_item

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
    st.markdown("---")
    st.subheader("🤖 作品タイトルのプロンプト作成")

    # 絞り込み後のデータ（query_df）から購入者数（_buy_num）が多い順に上位10件を自動抽出（バグ修正）
    if not query_df.empty:
        candidate_items = query_df.sort_values(by="_buy_num", ascending=False).head(10)
    else:
        candidate_items = pd.DataFrame()

    if candidate_items.empty:
        st.warning("⚠️ 参考データが見つかりませんでした。フィルターを緩めてみてください。")
    else:
        st.markdown("市場の人気を参考に、タイトルや紹介文を作成します。")
        
        my_work_description = st.text_area(
    "📝 あなたの作品の説明・特徴・こだわり", 
    value="",
    height=150,
    help="使用している作品のジャンルや名前、デザインの特徴、こだわりなどを自由に入力してください。"
)
        
        generate_btn = st.button("🚀 タイトル提案のプロンプト作成", type="primary")
# =================================================================
# 🛍️ ボタン1: 市場10選を分析してタイトルを提案してもらう
# =================================================================        
        if generate_btn:
            with st.spinner("📝 AI用のプロンプトを作成中..."):
                
                # 10件の売れ筋データ（candidate_items）からタイトル一覧のテキストを作成
                items_summary = ""
                for _, row in candidate_items.iterrows():
                    items_summary += f"・{row['商品名']} (購入者数: {row['_buy_num']}人)\n"
                    
                # ChatGPTやGeminiにそのまま貼り付けられる完成形プロンプトを組み立て
                final_prompt = f"""あなたはハンドメイドマーケット（Creemaやminne）の市場リサーチとコピーライティングのプロフェッショナルです。
以下の【分析対象：売れている商品のタイトル一覧】と【出品する作品の情報】を元に、売れる商品タイトルを考えてください。

---
【分析対象：売れている商品のタイトル一覧】
{items_summary}
---
【出品する作品の情報】
■作品の説明・特徴・こだわり:
{my_work_description}
---

以下の構成で出力してください。

### 1. 売れている商品のタイトル分析
* **よく入っているキーワード**: 10件の売れているタイトルから、特に多用されている、または重要度の高いキーワードを5つ抽出して解説してください。
* **全体の傾向とアドバイス**: 売れている作品の「キーワードの並び順」や「フック（記号や訴求点）」の傾向、新作を出品する際のアドバイスを詳しく教えてください。

### 2. 新作商品タイトル案（3選）
分析結果に基づき、クリックされやすいタイトルを以下の3つの切り口で提案してください。
1. **【検索ボリューム重視】**: 上位キーワードを戦略的に盛り込んだ、検索に引っかかりやすいタイトル。
2. **【情緒的訴求重視】**: ユーザーのこだわりや作品の魅力を最大限に伝える、ストーリー性を重視したタイトル。
3. **【トレンド融合型】**: 今回分析したヒット作品の構成を模倣しつつ、新作の特徴を掛け合わせたバランス型。
"""
            
            # デザイン枠（ai-box）の中に、完成したプロンプトを表示
            st.subheader("📋 AI用コピーテキストの作成完了")
            st.success("✨ 下の枠内のテキストをすべてコピーして、ChatGPTやGeminiのチャット欄に貼り付けてください。")
            
            # コピーしやすいように大きなテキストエリアで表示
            st.text_area("以下の文章を丸ごとコピーしてください：", value=final_prompt, height=450)
            st.markdown('</div>', unsafe_allow_html=True)
# 💡 検索後（データが存在する場合）のみエリア全体を表示
if 'candidate_items' in locals() and not candidate_items.empty:

    # =================================================================
    # ✍️ ボタン2: 市場10選を分析して作品紹介文を提案してもらう
    # =================================================================
    st.write("---") # 区切り線
    st.subheader("✍️ 作品紹介文（説明文）のプロンプト作成")

    # 紹介文用のタイトル入力欄
    my_product_title = st.text_input(
        "🏷️ 出品する作品のタイトル（決まっている場合や、上記で決めたタイトルを入力してください）",
        value="", 
        help="AIが紹介文を作成する際に、このタイトルとの整合性を意識して文章を作ります。"
    )

    # 紹介文生成用のボタン（赤色に統一！）
    generate_desc_btn = st.button("🚀 市場10選を分析して作品紹介文を提案してもらう", type="primary")

    # 💡 【重要】ここから下の全ての処理を「ボタンを押した時だけ」の枠（ifの中）に正しく入れました
    if generate_desc_btn:
        with st.spinner("🕵️‍♂️ 市場10選の作品ページから、リアルタイムに紹介文を読み込んでいます（数秒かかります）..."):
            
            descriptions_summary = ""
        
            # 10件の商品を1つずつループ処理
            for i, row in candidate_items.iterrows():
                item_name = row['商品名']
                
                # データフレームにURLが入っている列を探す
                item_url = row.get('商品URL', row.get('URL', row.get('url', row.get('作品URL', None))))
                
                # もしURLが相対パスだった場合の対策
                if item_url and item_url.startswith('/'):
                    item_url = f"https://www.creema.jp{item_url}"
                    
                cleaned_desc = "（紹介文の取得に失敗しました）"
                
                # URLが正しく取得できている場合、その場でCreemaのページを読みにいきます
                if item_url:
                    try:
                        # 人間用のブラウザのふりをする設定
                        headers = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        }
                        # ページをダウンロード
                        response = requests.get(item_url, headers=headers, timeout=10)
                        if response.status_code == 200:
                            # BeautifulSoupでHTMLを解析
                            soup = BeautifulSoup(response.text, 'html.parser')
                            # Creemaの紹介文の目印（クラス名）を探す
                            desc_element = soup.find('div', class_='p-item-detail-description')
                            
                            if desc_element:
                                # タグを消し、<br>を綺麗な改行にしてテキストを抽出
                                raw_text = desc_element.get_text('\n', strip=True)
                                # 3つ以上連続する無駄な改行をすっきり整形
                                cleaned_desc = re.sub(r'\n{3,}', '\n\n', raw_text)
                    except Exception as e:
                        cleaned_desc = f"（通信エラーにより取得失敗: {str(e)}）"
                
                # 取得した紹介文をプロンプト用に積み上げる
                descriptions_summary += f"■人気商品{i+1}: {item_name}\n【紹介文】:\n{cleaned_desc}\n\n"
                
            # ChatGPTやGeminiにそのまま貼り付けられる完成形プロンプトを組み立て
            final_desc_prompt = f"""あなたはハンドメイドマーケット（Creemaやminne）で月商100万円以上を売り上げるトップクリエイターであり、お客様の心を動かすWEBライティングの専門家です。

以下の【分析対象：売れている商品の紹介文一覧】と【私の作品情報】を徹底的に分析し、お客様が思わず欲しくなる最高の「作品紹介文（商品説明文）」を作成するためのデータを抽出し、さらに紹介文を3パターン提案してください。

---
【分析対象：売れている商品の紹介文一覧】
{descriptions_summary}
---
【私の作品情報】
■作品のタイトル: {my_product_title}
■作品の説明・特徴・こだわり: 
{my_work_description}
---

以下の構成とルールを厳守して出力してください。

### 1. 人気商品の紹介文分析
* **文章構成の傾向**: 売れている作品が「どのような順番」で書かれているか、共通する構成の黄金ルートを解説してください。
* **多用されているキーワード・響く表現**: お客様の購買意欲をそそる魅力的な言い回しを抽出してください。
* **どのようなことが書いてあるか（内容の共通点）**: 売れている紹介文に必ず盛り込まれている内容をまとめてください。

### 2. 新作の作品紹介文の提案（3選）
分析した人気商品の紹介文の構成をベースに、以下の【スマホで読みやすくなる視覚的ルール】を徹底し、出品にそのままコピペできる紹介文を【3つの異なる雰囲気（上品で丁寧、物語調エモーショナル、日常使いカジュアル）】で提案してください。

💡【スマホで読みやすくなる視覚的ルール】：
・【見出し】には「◆ 〇〇〇 ◆」や「【〇〇〇】」を使い、どこに何が書いてあるか一目でわかるようにしてください。
・【改行】は、1～2文（スマホの画面で2～3行）ごとに「空行」を1行挟み、ギュッと詰まった壁のような文章にならないようにしてください。
・【区切り線】には「───」や「◇◆◇◆◇◆◇◆◇◆◇」を適切に使い、セクションを美しく区切ってください。
・【絵文字】は、Creemaで文字化けしない定番のもの（✨、📌、💎、🌿、🎁、⚠️など）を文頭や重要なポイントに散りばめ、カラフルで華やかにしてください。

⚠️【紹介文に必ず入れる必須要素】：
1. **購入検討者が抱えている「悩みや願望」の深い掘り下げ**
   （ただの表面的な悩みではなく、「夕方になると重だだるくて、周りに優しくできない」「健康グッズはオバサンっぽくて着けたくない」「不器用だから毎朝ブレスレットを着けるだけで爪が痛む・遅刻しそうになる」など、日常のリアルな葛藤やイライラに共感する文章にしてください）

2. **この商品を手に入れることで、お客様が到達する「最高の未来（ベネフィットとその結末）」**
   （「見るたびに癒される」の先の【その結果、人生がどう変わるか】まで想像力を膨らませてください。例：手元を見るたびに心に余裕が生まれる、身体がラクになることで一日中笑顔でいられて自分を好きになれるなど）

3. **お客様が実際に商品を使用している姿・着用シーンの具体的な描写**
   （その作品を使用した時にどんな気持ちになるかを、慌ただしい朝や、通勤途中、パソコン作業中、休日のカフェでゆっくりしている時など、映像で想像できるシチュエーションを必ず入れてください）

4. **人気商品の紹介文から学んだ「売れる構成とキーワード」**

### 3. 検索対策キーワード一覧（文末に配置）
* この商品をCreemaやminneで検索してもらうために、ハッシュタグや検索窓に入力されやすいキーワードを20個以上、スペース区切りでずらりと一覧化してください。
* ⚠️【最重要ルール】：出力するキーワード一覧からは、上記の【私の作品情報】の「作品のタイトル」および「作品の説明・特徴・こだわり」の本文中に【すでに含まれている単語・表現】を絶対に徹底的に排除（除外）してください。本文にない「新しい関連キーワード」「類語」「言い換え表現」「ターゲット層の属性」「季節・シーンの言葉」だけで構成してください。
"""

        # テキストエリアとボタンの表示
        st.subheader("📋 【作品紹介文用】AI用コピーテキスト")
        st.success("✨ 作品紹介文用のプロンプトが完成しました！下の枠内のテキストをすべてコピーして、ChatGPTやGeminiに貼り付けてください。")
        
        st.text_area("以下の文章を丸ごとコピーしてください：", value=final_desc_prompt, height=500, key="desc_prompt_area")
        
        # JavaScript用安全変換
        js_safe_prompt = final_desc_prompt.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
        
        # コピーボタンのHTML
        copy_button_html = f"""
        <div style="margin-top: -10px; margin-bottom: 20px;">
            <button id="copy-btn" style="
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
        document.getElementById('copy-btn').addEventListener('click', function() {{
            const textToCopy = `{js_safe_prompt}`;
            
            navigator.clipboard.writeText(textToCopy).then(function() {{
                const btn = document.getElementById('copy-btn');
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
        
        st.components.v1.html(copy_button_html, height=50)
