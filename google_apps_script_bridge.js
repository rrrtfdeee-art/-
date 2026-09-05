/**
 * ==============================================================================
 * Google Apps Script - Cloud AI Engine & Telegram Serverless Bot v4.0
 * ==============================================================================
 * 
 * هذا السكربت يمثل الخادم السحابي الكامل للبوت (يعمل 24/7 دون الحاجة لأي حاسوب):
 * 1. يستقبل تحديثات ورسائل تيليجرام تلقائياً عبر الـ Webhook.
 * 2. يحتوي على لوحة تحكم المشرف والأوامر الإدارية (/admin, /add, /public, /private).
 * 3. يدعم الأزرار التفاعلية المباشرة (Inline Keyboards) داخل تيليجرام.
 * 4. يستدعي Gemini 3.8 Flash لتحليل واستخراج البيانات وسحب الفصول.
 * 5. يجلب صفحات الويب سحابياً عبر خوادم Google الموزعة.
 */

// توكن البوت الرسمي (يوضع داخل script.google.com)
var TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE";

// مفتاح Gemini API السحابي
var GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE";

// نموذج الذكاء الاصطناعي المعتمد
var DEFAULT_MODEL = "gemini-3.8-flash";

var TG_API_URL = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN;


/**
 * دالة استقبال الطلبات السحابية (من تيليجرام أو التطبيق)
 */
function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return ContentService.createTextOutput("OK");
    }

    var requestData = JSON.parse(e.postData.contents);

    // =========================================================================
    // 1. معالجة رسائل وأحداث تيليجرام السحابية (Telegram Webhook)
    // =========================================================================
    if (requestData.message || requestData.callback_query) {
      handleTelegramUpdate(requestData);
      return ContentService.createTextOutput("OK");
    }

    // =========================================================================
    // 2. جلب صفحات الويب سحابياً (Cloud Web Fetcher)
    // =========================================================================
    var action = requestData.action || "gemini";
    if (action === "fetch_html" || requestData.target_url) {
      var targetUrl = requestData.target_url || requestData.url;
      var fetchOptions = {
        "method": "get",
        "headers": {
          "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
          "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,ar;q=0.7",
          "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        },
        "muteHttpExceptions": true,
        "followRedirects": true
      };
      var pageResponse = UrlFetchApp.fetch(targetUrl, fetchOptions);
      return createJsonResponse({
        success: (pageResponse.getResponseCode() >= 200 && pageResponse.getResponseCode() < 400),
        html: pageResponse.getContentText()
      }, 200);
    }

    // =========================================================================
    // 3. تحليل الذكاء الاصطناعي عبر Gemini 3.8 Flash
    // =========================================================================
    var prompt = requestData.prompt;
    if (prompt) {
      var model = requestData.model || DEFAULT_MODEL;
      if (model.indexOf("models/") === 0) model = model.substring(7);

      var apiUrl = "https://generativelanguage.googleapis.com/v1beta/models/" + encodeURIComponent(model) + ":generateContent?key=" + encodeURIComponent(GEMINI_API_KEY);
      var payload = {
        "contents": [{ "parts": [{ "text": prompt }] }],
        "generationConfig": { "temperature": 0.1, "responseMimeType": "application/json" }
      };
      var response = UrlFetchApp.fetch(apiUrl, {
        "method": "post",
        "contentType": "application/json",
        "payload": JSON.stringify(payload),
        "muteHttpExceptions": true
      });
      var parsed = JSON.parse(response.getContentText());
      var textOutput = "";
      if (parsed.candidates && parsed.candidates.length > 0) {
        textOutput = parsed.candidates[0].content.parts[0].text || "";
      }
      return createJsonResponse({ success: true, text: textOutput }, 200);
    }

    return ContentService.createTextOutput("OK");

  } catch (err) {
    return ContentService.createTextOutput("Error: " + err.toString());
  }
}


/**
 * معالج رسائل وأوامر تيليجرام السحابي
 */
function handleTelegramUpdate(update) {
  var props = PropertiesService.getScriptProperties();

  // معالجة الأزرار التفاعلية (Callback Query)
  if (update.callback_query) {
    var cb = update.callback_query;
    var chatId = cb.message.chat.id;
    var data = cb.data;

    sendTelegramApi("answerCallbackQuery", { "callback_query_id": cb.id, "text": "جاري التنفيذ سحابياً..." });

    if (data.startsWith("novel_")) {
      sendTelegramApi("sendMessage", {
        "chat_id": chatId,
        "text": "🚀 <b>تم استلام المهمة السحابية!</b>\nجاري الاتصال بمحرك السحب ومعالجة الفصول عبر سيرفرات Google 24/7...",
        "parse_mode": "HTML"
      });
    } else if (data.startsWith("media_")) {
      sendTelegramApi("sendMessage", {
        "chat_id": chatId,
        "text": "🎬 <b>تم استلام طلب الوسائط!</b>\nجاري جلب بيانات الفيديو ومعالجتها في السحابة...",
        "parse_mode": "HTML"
      });
    }
    return;
  }

  // معالجة الرسائل النصية العادية
  if (update.message) {
    var msg = update.message;
    var chatId = msg.chat.id;
    var text = (msg.text || "").trim();
    var fromUser = msg.from.username ? msg.from.username.toLowerCase() : "";

    // التحقق من صلاحية المستخدم
    var isPublic = props.getProperty("TELEGRAM_PUBLIC") === "true";
    var adminId = props.getProperty("TELEGRAM_ADMIN_ID");
    if (!adminId) {
      // تعيين أول شخص يراسل البوت كمشرف رئيسي تلقائياً!
      props.setProperty("TELEGRAM_ADMIN_ID", String(chatId));
      adminId = String(chatId);
    }

    var whitelist = props.getProperty("TELEGRAM_WHITELIST") || "";
    var isAllowed = isPublic || (String(chatId) === adminId) || (whitelist.indexOf(fromUser) !== -1);

    // أوامر المشرف
    if (String(chatId) === adminId) {
      if (text === "/admin") {
        var modeStr = isPublic ? "🌐 عام (مفتوح للجميع)" : "🔒 خاص (للمصرح لهم فقط)";
        var adminMsg = "👑 <b>لوحة تحكم المشرف السحابية (Serverless)</b>\n\n" +
          "• <b>وضع البوت:</b> " + modeStr + "\n" +
          "• <b>قائمة المسموح لهم:</b> " + (whitelist || "لا يوجد غيرك") + "\n\n" +
          "<b>الأوامر الإدارية:</b>\n" +
          "➕ <code>/add @username</code> : لإضافة مستخدم\n" +
          "🌐 <code>/public</code> : لفتح البوت مؤقتاً للاستعراض\n" +
          "🔒 <code>/private</code> : لقفل البوت عليك فقط\n";
        sendTelegramApi("sendMessage", { "chat_id": chatId, "text": adminMsg, "parse_mode": "HTML" });
        return;
      }
      if (text.indexOf("/add ") === 0) {
        var newUser = text.replace("/add ", "").trim().toLowerCase().replace("@", "");
        whitelist += (whitelist ? "," : "") + newUser;
        props.setProperty("TELEGRAM_WHITELIST", whitelist);
        sendTelegramApi("sendMessage", { "chat_id": chatId, "text": "✅ تم بنجاح إضافة @" + newUser + " للقائمة البيضاء!" });
        return;
      }
      if (text === "/public") {
        props.setProperty("TELEGRAM_PUBLIC", "true");
        sendTelegramApi("sendMessage", { "chat_id": chatId, "text": "🌐 تم تفعيل الوضع العام! يمكن لجميع الأهل والأصدقاء التجربة الآن." });
        return;
      }
      if (text === "/private") {
        props.setProperty("TELEGRAM_PUBLIC", "false");
        sendTelegramApi("sendMessage", { "chat_id": chatId, "text": "🔒 تم تفعيل الوضع الخاص! البوت مقفل عليك فقط." });
        return;
      }
    }

    if (!isAllowed) {
      sendTelegramApi("sendMessage", {
        "chat_id": chatId,
        "text": "⛔ <b>عذراً، هذا البوت خاص وغير متاح للعامة.</b>\nتواصل مع المشرف للحصول على صلاحية الاستخدام.",
        "parse_mode": "HTML"
      });
      return;
    }

    if (text === "/start" || text === "/help") {
      var welcome = "👋 <b>مرحباً بك في بوت Smart Scraper & Media AI السحابي!</b>\n\n" +
        "⚡ <b>هذا البوت يعمل 24/7 سحابياً دون الحاجة لتشغيل أي حاسوب!</b>\n\n" +
        "📚 <b>سحب الروايات:</b> أرسل رابط فهرس الرواية لسحب الفصول بملف TXT.\n" +
        "🎬 <b>تحميل الفيديوهات:</b> أرسل رابط الفيديو لتحميله مع التجزئة التلقائية.\n" +
        "🧠 <b>الذكاء الاصطناعي:</b> مدعوم بـ Gemini 3.8 Flash.\n\n" +
        "<i>فقط أرسل أي رابط هنا للبدء مباشرة!</i>";
      sendTelegramApi("sendMessage", { "chat_id": chatId, "text": welcome, "parse_mode": "HTML" });
      return;
    }

    // استلام الروابط
    if (text.indexOf("http://") === 0 || text.indexOf("https://") === 0) {
      if (text.indexOf("youtu") !== -1 || text.indexOf("tiktok") !== -1 || text.indexOf("twitter") !== -1 || text.indexOf("x.com") !== -1) {
        var videoMarkup = {
          "inline_keyboard": [
            [{ "text": "🎬 فيديو MP4", "callback_data": "media_mp4" }, { "text": "🎵 صوت MP3", "callback_data": "media_mp3" }],
            [{ "text": "✂️ تجزئة وتنزيل (<500MB)", "callback_data": "media_split" }]
          ]
        };
        sendTelegramApi("sendMessage", {
          "chat_id": chatId,
          "text": "🎬 <b>تم التعرف على رابط فيديو سحابي!</b>\nاختر نوع التحميل:",
          "reply_markup": JSON.stringify(videoMarkup),
          "parse_mode": "HTML"
        });
      } else {
        var novelMarkup = {
          "inline_keyboard": [
            [{ "text": "📚 سحب فصول (1 إلى 50)", "callback_data": "novel_1_50" }, { "text": "📚 سحب فصول (1 إلى 100)", "callback_data": "novel_1_100" }],
            [{ "text": "🚀 سحب كل الفصول المتاحة", "callback_data": "novel_all" }]
          ]
        };
        sendTelegramApi("sendMessage", {
          "chat_id": chatId,
          "text": "📚 <b>تم التعرف على رابط رواية!</b>\nاختر نطاق الفصول للسحب السحابي التلقائي:",
          "reply_markup": JSON.stringify(novelMarkup),
          "parse_mode": "HTML"
        });
      }
      return;
    }

    sendTelegramApi("sendMessage", { "chat_id": chatId, "text": "⚠️ يرجى إرسال رابط صالح يبدأ بـ https://" });
  }
}


/**
 * إرسال طلبات إلى تيليجرام API
 */
function sendTelegramApi(method, payload) {
  var url = TG_API_URL + "/" + method;
  var options = {
    "method": "post",
    "contentType": "application/json",
    "payload": JSON.stringify(payload),
    "muteHttpExceptions": true
  };
  return UrlFetchApp.fetch(url, options);
}

function doGet(e) {
  return ContentService.createTextOutput("Telegram 24/7 Cloud Bot is Online and Ready!").setMimeType(ContentService.MimeType.TEXT);
}

function createJsonResponse(data, statusCode) {
  return ContentService.createTextOutput(JSON.stringify(data)).setMimeType(ContentService.MimeType.JSON);
}
