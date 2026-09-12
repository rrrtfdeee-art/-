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

    // =========================================================================
    // 4. تفريغ وضخ الفصول في شيت الأرشيف الخام (1v1V4) مع الترتيب الموضعي ومنع التكرار
    // =========================================================================
    if (action === "pushToRawArchive" || action === "upload_single_chapter") {
      var rawSsId = requestData.spreadsheetId || RAW_ARCHIVE_SPREADSHEET_ID;
      var chNum = requestData.chapter_number || requestData.chapterNumber || 0;
      var rawContent = requestData.content || requestData.rawText || "";
      var novelName = requestData.novel_name || requestData.novelName || "عام";
      var createdAt = requestData.createdAt || new Date().toISOString();
      var sourceUrl = requestData.source_url || requestData.sourceUrl || "";
      var pTitle = String(requestData.title || "").trim();

      // ضمان احتواء المحتوى على عنوان الفصل الأصلي إذا لم يكن موجوداً
      if (rawContent && pTitle && !rawContent.startsWith(pTitle)) {
        rawContent = pTitle + "\n\n" + rawContent;
      }
      
      var resInsert = insertOrUpdateChapterInSheet(rawSsId, "الورقة1", novelName, chNum, [chNum, rawContent, novelName, createdAt, sourceUrl]);
      return createJsonResponse({ status: "success", chapter: chNum, result: resInsert }, 200);
    }

    // =========================================================================
    // 5. الفرز الشامل ومنع التكرار الصارم لكافة الجداول الثلاثة (1v1V4, 1Fceh, 1HDj)
    // =========================================================================
    if (action === "sortAndDeduplicateAllSheets" || action === "sortSystemSheets") {
      var sortReport = runFullDeduplicationAndSortingNow();
      return createJsonResponse({ status: "success", results: sortReport }, 200);
    }

    // =========================================================================
    // 6. كاشف فجوات جدول الأرشيف واقتراح التنزيل (Archive Gap Detector)
    // =========================================================================
    if (action === "detectArchiveGaps" || action === "getArchiveGaps") {
      var nName = requestData.novel_name || requestData.novelName || "";
      var totCh = requestData.total_chapters || requestData.totalChapters || 0;
      var gapsReport = detectArchiveGapsReport(nName, totCh);
      return createJsonResponse({ status: "success", gaps: gapsReport }, 200);
    }

    // =========================================================================
    // 7. كاشف القيم المتطرفة الدنيا الإحصائي لشيت الأرشيف (العمود B)
    // =========================================================================
    if (action === "detectSheetExtremeOutliers" || action === "detectSheetOutliers") {
      var nName = requestData.novel_name || requestData.novelName || "";
      var ssId = requestData.spreadsheetId || RAW_ARCHIVE_SPREADSHEET_ID;
      var sName = requestData.sheet_name || requestData.sheetName || "الورقة1";
      var outliersReport = detectSheetExtremeOutliers(nName, ssId, sName);
      return createJsonResponse({ status: "success", report: outliersReport }, 200);
    }

    // =========================================================================
    // 8. تعديل واستبدال مباشر لنفس خلية المحتوى (العمود B) في شيت الأرشيف
    // =========================================================================
    if (action === "updateChapterContentInPlace" || action === "update_chapter_content") {
      var ssId = requestData.spreadsheetId || RAW_ARCHIVE_SPREADSHEET_ID;
      var sName = requestData.sheet_name || requestData.sheetName || "الورقة1";
      var nName = requestData.novel_name || requestData.novelName || "عام";
      var chNum = requestData.chapter_number || requestData.chapterNumber || 0;
      var newContent = requestData.content || requestData.rawText || "";
      var pTitle = String(requestData.title || "").trim();

      if (newContent && pTitle && !newContent.startsWith(pTitle)) {
        newContent = pTitle + "\n\n" + newContent;
      }

      var resUpdate = updateChapterContentInPlace(ssId, sName, nName, chNum, newContent);
      return createJsonResponse({ status: "success", result: resUpdate }, 200);
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


/**
 * ==============================================================================
 * NSW System Sheets Sorter, Strict Deduplicator & Gap Detector v5.0
 * ==============================================================================
 * هذا الملف مسؤول عن:
 * 1. منع التكرار الصارم في الجداول الثلاثة (الأرشيف، الترجمة، النشر): فصل واحد فقط لكل (رواية + رقم فصل).
 *    - الفصول ذات الأجزاء (مثل 22.5 أو تكملة) تُعامل كفصول جديدة مستقلة تماماً.
 * 2. الترتيب الموضعي الدقيق (In-Place Ordered Insertion):
 *    - عند إدراج فصل جديد لرواية A (مثلاً 550)، يتم وضعه مباشرة بعد 549 وقبل بداية الرواية B.
 * 3. دالة فرز وتنظيف شاملة وفورية لكافة الجداول الثلاثة (1v1V4, 1Fceh, 1HDj).
 * 4. كاشف فجوات الأرشيف الذكي (Archive Gap Detector): اكتشاف الفجوات مثل (4, 6, 8, 12 -> 1-3, 5, 7, 9-11, 13-N).
 * ==============================================================================
 */

// المعرفات المركزية للجداول الثلاثة
var RAW_ARCHIVE_SPREADSHEET_ID = "1v1V4_rQukDs3oCe8Z4Izvni3uCx91iKmSVNOm4A3mH0";
var TRANSLATE_SPREADSHEET_ID = "1FcehVXh-GLlZGePTm2nm13N932qcFeT0uGuOsXRFXpI";
var PUBLISH_QUEUE_SPREADSHEET_ID = "1HDjYu6EypdiNfoawJ2s7nQcRJiGsfJ5bNefcEy0QhFE";

// أسماء الروايات الرسمية المسجلة للتعرف الذكي
var KNOWN_NOVEL_NAMES = [
  "After Severing Ties",
  "المزارع الخبير في المدرسة الابتدائية",
  "رماد النبل وجمر التمرد",
  "نظام الانعكاس لا يظهر إلا بعد بلوغ مرحلة الماهايانا",
  "Only at the Mahayana Stage Does the Reversal System Appear",
  "الوريث المنبوذ"
];


// ==============================================================================
// 1. دوال استخراج المفاتيح والترتيب والتمييز بين الأرقام والأجزاء
// ==============================================================================

/**
 * استخراج مفتاح الفصل للفرز والترتيب (يدعم الكسور مثل 22.5 والتكملة)
 */
function parseChapterSortKey(val) {
  var s = String(val || "").trim();
  var match = s.match(/(\d+(?:\.\d+)?)/);
  if (match) {
    var num = parseFloat(match[1]);
    var suffix = s.substring(match.index + match[0].length).trim().toLowerCase();
    return { num: num, suffix: suffix, raw: s };
  }
  return { num: 999999, suffix: s.toLowerCase(), raw: s };
}

/**
 * توليد مفتاح التحقق من التكرار الصارم:
 * يجمع اسم الرواية ورقم الفصل مع الجزء العشري أو اللاحقة.
 * مثال:
 * - الرواية A + فصل 22 -> "novel_a__22"
 * - الرواية A + فصل 22.5 -> "novel_a__22.5" (مفتاح مختلف لا يتداخل مع 22)
 * - الرواية A + فصل 22 (تكملة) -> "novel_a__22_تكملة" (مفتاح مختلف)
 */
function getChapterDeduplicationKey(novelName, chapterVal) {
  var cleanNovel = String(novelName || "عام").trim().toLowerCase();
  var parsed = parseChapterSortKey(chapterVal);
  var numStr = String(parsed.num);
  var suffixStr = parsed.suffix ? "_" + parsed.suffix.replace(/\s+/g, "") : "";
  return cleanNovel + "__" + numStr + suffixStr;
}

/**
 * تحديد أعمدة (رقم الفصل، اسم الرواية، المحتوى) تلقائياً من صف العناوين أو البيانات
 */
function detectSheetColumns(sheet, headers) {
  var chapCol = 0;
  var novelCol = -1;
  var contentCol = 1;

  for (var c = 0; c < headers.length; c++) {
    var h = String(headers[c] || "").trim().toLowerCase();
    if (h.includes("فصل") || h.includes("chap") || h === "number" || h === "رقم" || h === "chapternum") {
      chapCol = c;
    } else if (h.includes("رواية") || h.includes("novel") || h.includes("book") || h.includes("اسم الرواية")) {
      novelCol = c;
    } else if (h.includes("نص") || h.includes("content") || h.includes("html") || h.includes("raw") || h.includes("المحتوى")) {
      contentCol = c;
    }
  }

  // في حال لم يتم العثور على عمود الرواية بالاسم، نبحث في عينات البيانات
  if (novelCol === -1) {
    var sampleRows = sheet.getRange(2, 1, Math.min(10, Math.max(1, sheet.getLastRow() - 1)), headers.length).getValues();
    for (var colIdx = 0; colIdx < headers.length; colIdx++) {
      for (var rowIdx = 0; rowIdx < sampleRows.length; rowIdx++) {
        var cellVal = String(sampleRows[rowIdx][colIdx] || "").trim();
        for (var kn = 0; kn < KNOWN_NOVEL_NAMES.length; kn++) {
          if (cellVal.toLowerCase().includes(KNOWN_NOVEL_NAMES[kn].toLowerCase())) {
            novelCol = colIdx;
            break;
          }
        }
        if (novelCol !== -1) break;
      }
      if (novelCol !== -1) break;
    }
  }

  // افتراضيات قياسية إذا تعذر الاكتشاف
  if (novelCol === -1) {
    var sheetName = sheet.getName().toLowerCase();
    if (sheetName.includes("الورقة1") || sheetName.includes("archive")) {
      novelCol = 2; // في شيت 1v1V4 العمود C هو اسم الرواية
    } else {
      novelCol = headers.length > 7 ? 7 : (headers.length > 1 ? 1 : 0);
    }
  }

  return { chapCol: chapCol, novelCol: novelCol, contentCol: contentCol };
}


// ==============================================================================
// 2. الإدراج الموضعي الذكي ومنع التكرار اللحظي (In-Place Ordered Insertion)
// ==============================================================================

/**
 * إدراج فصل جديد في مكانه المرتب رياضياً بدقة داخل كتلة الرواية مع منع التكرار:
 * إذا كانت الرواية A تنتهي بالفصل 549 وتحتها الرواية B، يتم إدراج 550 مباشرة بعد 549!
 */
function insertOrUpdateChapterInSheet(spreadsheetId, sheetName, novelName, chapterNum, rowData) {
  var ss = SpreadsheetApp.openById(spreadsheetId);
  var sheet = sheetName ? (ss.getSheetByName(sheetName) || ss.getSheets()[0]) : ss.getSheets()[0];
  var lastRow = sheet.getLastRow();

  // إذا كان الجدول فارغاً أو به رأس فقط
  if (lastRow <= 1) {
    sheet.appendRow(rowData);
    SpreadsheetApp.flush();
    return { status: "appended_initial", row: lastRow + 1 };
  }

  var numCols = sheet.getLastColumn();
  var headers = sheet.getRange(1, 1, 1, numCols).getValues()[0];
  var colCfg = detectSheetColumns(sheet, headers);
  var targetKey = getChapterDeduplicationKey(novelName, chapterNum);
  var targetSort = parseChapterSortKey(chapterNum);
  var cleanNovelTarget = String(novelName || "عام").trim().toLowerCase();

  var allData = sheet.getRange(2, 1, lastRow - 1, numCols).getValues();
  var existingRowIndex = -1; // 0-based in allData
  var novelRowIndices = []; // indices of rows belonging to this novel

  for (var i = 0; i < allData.length; i++) {
    var rowNovel = String(allData[i][colCfg.novelCol] || "").trim().toLowerCase();
    var rowChap = allData[i][colCfg.chapCol];
    var currentKey = getChapterDeduplicationKey(rowNovel, rowChap);

    // 1. فحص التكرار الصارم
    if (currentKey === targetKey) {
      existingRowIndex = i;
      break;
    }

    // رصد سطور الرواية المستهدفة
    if (rowNovel === cleanNovelTarget || (cleanNovelTarget.length > 3 && rowNovel.includes(cleanNovelTarget))) {
      novelRowIndices.push(i);
    }
  }

  // حالة 1: الفصل موجود مسبقاً -> منع التكرار وتحديث المحتوى إذا كان الجديد أكمل
  if (existingRowIndex !== -1) {
    var actualSheetRow = existingRowIndex + 2; // +2 لأن allData تبدأ من السطر 2
    var oldContent = String(allData[existingRowIndex][colCfg.contentCol] || "");
    var newContent = String(rowData[colCfg.contentCol] || "");

    // تحديث السطر إذا كان المحتوى الجديد موجوداً وكاملاً
    if (newContent.length >= oldContent.length || oldContent.length < 100) {
      sheet.getRange(actualSheetRow, 1, 1, rowData.length).setValues([rowData]);
      SpreadsheetApp.flush();
      return { status: "updated_duplicate_prevented", row: actualSheetRow, chapter: chapterNum };
    }
    return { status: "already_exists_kept_existing", row: actualSheetRow, chapter: chapterNum };
  }

  // حالة 2: الرواية موجودة مسبقاً في الجدول -> إدراج الفصل في مكانه التسلسلي بدقة
  if (novelRowIndices.length > 0) {
    var insertAfterSheetRow = -1;
    var insertBeforeSheetRow = -1;

    // البحث عن الموقع الدقيق للفصل الجديد بين فصول الرواية
    for (var k = 0; k < novelRowIndices.length; k++) {
      var rIdx = novelRowIndices[k];
      var rChapVal = allData[rIdx][colCfg.chapCol];
      var rSort = parseChapterSortKey(rChapVal);

      if (rSort.num < targetSort.num || (rSort.num === targetSort.num && rSort.suffix < targetSort.suffix)) {
        insertAfterSheetRow = rIdx + 2; // السطر في الشيت
      } else {
        insertBeforeSheetRow = rIdx + 2;
        break;
      }
    }

    if (insertAfterSheetRow !== -1) {
      // إدراج صف جديد بعد الفصل السابق مباشرة
      sheet.insertRowAfter(insertAfterSheetRow);
      sheet.getRange(insertAfterSheetRow + 1, 1, 1, rowData.length).setValues([rowData]);
      SpreadsheetApp.flush();
      return { status: "inserted_in_place_after", row: insertAfterSheetRow + 1, chapter: chapterNum };
    } else if (insertBeforeSheetRow !== -1) {
      // إدراج صف جديد قبل أول فصل أكبر منه
      sheet.insertRowBefore(insertBeforeSheetRow);
      sheet.getRange(insertBeforeSheetRow, 1, 1, rowData.length).setValues([rowData]);
      SpreadsheetApp.flush();
      return { status: "inserted_in_place_before", row: insertBeforeSheetRow, chapter: chapterNum };
    }
  }

  // حالة 3: رواية جديدة تماماً في الجدول -> الإلحاق في الأسفل لإنشاء كتلتها الخاصة
  sheet.appendRow(rowData);
  SpreadsheetApp.flush();
  return { status: "appended_new_novel", row: sheet.getLastRow(), chapter: chapterNum };
}


// ==============================================================================
// 3. محرك الفرز الشامل ومنع التكرار لكافة الجداول الثلاثة (Full Sorter & Deduplicator)
// ==============================================================================

/**
 * فرز وتنظيف وتصفية جدول محدد بالكامل:
 * - حذف كافة الصفوف المكررة (مع الاحتفاظ بالمحتوى الأطول والأكمل).
 * - تجميع الفصول حسب الرواية.
 * - ترتيب فصول كل رواية تصاعدياً من 1 إلى N بدقة متناهية.
 */
function sortAndDeduplicateSingleSheet(sheet) {
  var lastRow = sheet.getLastRow();
  var lastCol = sheet.getLastColumn();
  if (lastRow <= 2) {
    return { status: "skipped_too_small", rows: lastRow };
  }

  var headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
  var colCfg = detectSheetColumns(sheet, headers);
  var rawData = sheet.getRange(2, 1, lastRow - 1, lastCol).getValues();

  var novelGroups = {}; // novelName -> array of row objects
  var novelOrder = []; // حفظ ترتيب ظهور الروايات

  var duplicatesCount = 0;
  var seenKeys = {}; // key -> bestRowObject

  for (var i = 0; i < rawData.length; i++) {
    var row = rawData[i];
    var chapVal = row[colCfg.chapCol];
    if (chapVal === "" || chapVal === null || chapVal === undefined) continue;

    var rawNovel = String(row[colCfg.novelCol] || "").trim();
    if (!rawNovel || rawNovel === "عام") {
      // محاولة استخراج الاسم من العنوان إن وُجد
      for (var kn = 0; kn < KNOWN_NOVEL_NAMES.length; kn++) {
        if (row.join(" ").toLowerCase().includes(KNOWN_NOVEL_NAMES[kn].toLowerCase())) {
          rawNovel = KNOWN_NOVEL_NAMES[kn];
          row[colCfg.novelCol] = rawNovel;
          break;
        }
      }
    }
    rawNovel = rawNovel || "رواية عامة";

    var dupKey = getChapterDeduplicationKey(rawNovel, chapVal);
    var contentLen = String(row[colCfg.contentCol] || "").length;
    var sortKey = parseChapterSortKey(chapVal);

    var rowObj = {
      data: row,
      novel: rawNovel,
      chapNum: sortKey.num,
      sortKey: sortKey,
      contentLen: contentLen,
      dupKey: dupKey
    };

    if (seenKeys[dupKey]) {
      duplicatesCount++;
      // المقارنة بين المكررين: الاحتفاظ بصاحب المحتوى الأكبر
      if (contentLen > seenKeys[dupKey].contentLen) {
        seenKeys[dupKey].data = row;
        seenKeys[dupKey].contentLen = contentLen;
      }
    } else {
      seenKeys[dupKey] = rowObj;
      if (!novelGroups[rawNovel]) {
        novelGroups[rawNovel] = [];
        novelOrder.push(rawNovel);
      }
      novelGroups[rawNovel].push(rowObj);
    }
  }

  // إعادة فرز كل رواية تصاعدياً من 1 إلى N
  var finalSortedRows = [];
  for (var nIdx = 0; nIdx < novelOrder.length; nIdx++) {
    var nvName = novelOrder[nIdx];
    var chapsList = novelGroups[nvName];

    chapsList.sort(function(a, b) {
      if (a.sortKey.num !== b.sortKey.num) {
        return a.sortKey.num - b.sortKey.num;
      }
      return a.sortKey.suffix.localeCompare(b.sortKey.suffix);
    });

    for (var cIdx = 0; cIdx < chapsList.length; cIdx++) {
      finalSortedRows.push(chapsList[cIdx].data);
    }
  }

  // مسح البيانات القديمة وكتابة البيانات المفرزة والمنظفة في دفعة واحدة
  sheet.getRange(2, 1, lastRow - 1, lastCol).clearContent();
  if (finalSortedRows.length > 0) {
    sheet.getRange(2, 1, finalSortedRows.length, lastCol).setValues(finalSortedRows);
  }
  SpreadsheetApp.flush();

  return {
    status: "success",
    initialRows: lastRow - 1,
    duplicatesRemoved: duplicatesCount,
    finalRows: finalSortedRows.length,
    novelsCount: novelOrder.length
  };
}

/**
 * 🚀 الدالة الكبرى: تشغيل الفرز ومنع التكرار على الجداول الثلاثة فورياً
 */
function runFullDeduplicationAndSortingNow() {
  var report = {
    timestamp: new Date().toISOString(),
    sheets: {}
  };

  // 1. جدول الأرشيف الخام (1v1V4)
  try {
    var ssArchive = SpreadsheetApp.openById(RAW_ARCHIVE_SPREADSHEET_ID);
    var archiveSheet = ssArchive.getSheetByName("الورقة1") || ssArchive.getSheets()[0];
    report.sheets["1v1V4_Archive"] = sortAndDeduplicateSingleSheet(archiveSheet);
  } catch (eArch) {
    report.sheets["1v1V4_Archive"] = { error: eArch.message };
  }

  // 2. جدول الترجمة والتدقيق (1Fceh)
  try {
    var ssTrans = SpreadsheetApp.openById(TRANSLATE_SPREADSHEET_ID);
    var allTransSheets = ssTrans.getSheets();
    for (var s = 0; s < allTransSheets.length; s++) {
      var sh = allTransSheets[s];
      var sName = sh.getName();
      if (sName.toLowerCase().includes("queue") || sName.includes("الورقة") || sName === "TranslateQueue" || sName === "ReviewQueue") {
        report.sheets["1Fceh_" + sName] = sortAndDeduplicateSingleSheet(sh);
      }
    }
  } catch (eTrans) {
    report.sheets["1Fceh_Translate"] = { error: eTrans.message };
  }

  // 3. جدول النشر وطابور المدونة (1HDj)
  try {
    var ssPub = SpreadsheetApp.openById(PUBLISH_QUEUE_SPREADSHEET_ID);
    var allPubSheets = ssPub.getSheets();
    for (var p = 0; p < allPubSheets.length; p++) {
      var pSh = allPubSheets[p];
      var pName = pSh.getName();
      if (pName.toLowerCase().includes("queue") || pName.includes("published") || pName === "Queue") {
        report.sheets["1HDj_" + pName] = sortAndDeduplicateSingleSheet(pSh);
      }
    }
  } catch (ePub) {
    report.sheets["1HDj_Publish"] = { error: ePub.message };
  }

  Logger.log("🎉 [تقرير الترتيب ومنع التكرار الشامل]:\n" + JSON.stringify(report, null, 2));
  return report;
}


// ==============================================================================
// 4. كاشف فجوات جدول الأرشيف واقتراح التنزيل (Archive Gap Detector)
// ==============================================================================

/**
 * فحص جدول الأرشيف (1v1V4) لرواية معينة واستخراج كافة الفصول المفقودة والفجوات بدقة
 * مثال: الفصول المتوفرة 4، 6، 8، 12
 * النتيجة: فجوة 1-3، فجوة 5، فجوة 7، فجوة 9-11، وفجوة 13 إلى النهاية.
 */
function detectArchiveGapsReport(novelName, totalChapters) {
  var ss = SpreadsheetApp.openById(RAW_ARCHIVE_SPREADSHEET_ID);
  var sheet = ss.getSheetByName("الورقة1") || ss.getSheets()[0];
  var lastRow = sheet.getLastRow();

  if (lastRow <= 1) {
    var tot = totalChapters || 100;
    return {
      novel_name: novelName,
      archived_count: 0,
      existing_chapters: [],
      missing_ranges: [{ from: 1, to: tot, label: "1-" + tot }],
      total_missing: tot
    };
  }

  var numCols = sheet.getLastColumn();
  var headers = sheet.getRange(1, 1, 1, numCols).getValues()[0];
  var colCfg = detectSheetColumns(sheet, headers);
  var data = sheet.getRange(2, 1, lastRow - 1, numCols).getValues();

  var cleanTarget = String(novelName || "").trim().toLowerCase();
  var existingSet = {};

  for (var i = 0; i < data.length; i++) {
    var rowNovel = String(data[i][colCfg.novelCol] || "").trim().toLowerCase();
    if (!cleanTarget || rowNovel.includes(cleanTarget) || cleanTarget.includes(rowNovel)) {
      var chVal = data[i][colCfg.chapCol];
      var p = parseChapterSortKey(chVal);
      if (p.num > 0 && p.num < 999990) {
        existingSet[Math.floor(p.num)] = true;
      }
    }
  }

  var existingNums = Object.keys(existingSet).map(function(k) { return parseInt(k, 10); });
  existingNums.sort(function(a, b) { return a - b; });

  if (existingNums.length === 0) {
    var defTot = totalChapters || 100;
    return {
      novel_name: novelName,
      archived_count: 0,
      existing_chapters: [],
      missing_ranges: [{ from: 1, to: defTot, label: "1-" + defTot }],
      total_missing: defTot
    };
  }

  var maxExisting = existingNums[existingNums.length - 1];
  var targetLimit = Math.max(maxExisting, totalChapters || maxExisting);

  var missingNums = [];
  for (var c = 1; c <= targetLimit; c++) {
    if (!existingSet[c]) {
      missingNums.push(c);
    }
  }

  // تجميع الأرقام المفقودة في نطاقات متصلة (Ranges)
  var ranges = [];
  if (missingNums.length > 0) {
    var rangeStart = missingNums[0];
    var prev = missingNums[0];

    for (var m = 1; m < missingNums.length; m++) {
      var curr = missingNums[m];
      if (curr === prev + 1) {
        prev = curr;
      } else {
        ranges.push({
          from: rangeStart,
          to: prev,
          label: (rangeStart === prev) ? String(rangeStart) : (rangeStart + "-" + prev)
        });
        rangeStart = curr;
        prev = curr;
      }
    }
    ranges.push({
      from: rangeStart,
      to: prev,
      label: (rangeStart === prev) ? String(rangeStart) : (rangeStart + "-" + prev)
    });
  }

  return {
    novel_name: novelName,
    archived_count: existingNums.length,
    min_chapter: existingNums[0],
    max_chapter: maxExisting,
    target_limit: targetLimit,
    missing_ranges: ranges,
    total_missing: missingNums.length
  };
}


// ==============================================================================
// 5. كاشف القيم المتطرفة الدنيا الإحصائي والتعديل المباشر لشيت الأرشيف (العمود B)
// ==============================================================================

/**
 * كاشف القيم المتطرفة الدنيا الإحصائي لفصول شيت الأرشيف (العمود B):
 * يحسب المتوسط الحسابي، الوسيط، الربيعيات (Q1, Q3, IQR)، والحد الأدنى المتطرف
 */
function detectSheetExtremeOutliers(novelName, spreadsheetId, sheetName) {
  var ssId = spreadsheetId || RAW_ARCHIVE_SPREADSHEET_ID;
  var ss = SpreadsheetApp.openById(ssId);
  var sheet = sheetName ? (ss.getSheetByName(sheetName) || ss.getSheets()[0]) : ss.getSheets()[0];
  var lastRow = sheet.getLastRow();

  if (lastRow <= 1) {
    return { error: "الجدول فارغ أو لا يحتوي على فصول", total_chapters: 0, outliers: [] };
  }

  var numCols = sheet.getLastColumn();
  var headers = sheet.getRange(1, 1, 1, numCols).getValues()[0];
  var colCfg = detectSheetColumns(sheet, headers);
  var allData = sheet.getRange(2, 1, lastRow - 1, numCols).getValues();

  var cleanTarget = String(novelName || "").trim().toLowerCase();
  var chapterRows = [];
  var lengths = [];

  for (var i = 0; i < allData.length; i++) {
    var rowNovel = String(allData[i][colCfg.novelCol] || "").trim().toLowerCase();
    if (!cleanTarget || rowNovel.includes(cleanTarget) || cleanTarget.includes(rowNovel)) {
      var chVal = allData[i][colCfg.chapCol];
      var p = parseChapterSortKey(chVal);
      var content = String(allData[i][colCfg.contentCol] || "");
      var len = content.length;
      var actualRow = i + 2;

      chapterRows.push({
        row: actualRow,
        chapter_num: p.num,
        suffix: p.suffix,
        raw_val: chVal,
        length: len,
        novel: allData[i][colCfg.novelCol]
      });
      lengths.push(len);
    }
  }

  if (chapterRows.length === 0) {
    return { error: "لم يتم العثور على فصول للرواية المحددة", novel_name: novelName, total_chapters: 0, outliers: [] };
  }

  // حساب المتوسط الحسابي
  var sum = 0;
  for (var j = 0; j < lengths.length; j++) {
    sum += lengths[j];
  }
  var mean = sum / lengths.length;

  // حساب الوسيط والربيعيات
  var sortedLengths = lengths.slice().sort(function(a, b) { return a - b; });
  var n = sortedLengths.length;
  var median = (n % 2 === 0) ? (sortedLengths[n / 2 - 1] + sortedLengths[n / 2]) / 2 : sortedLengths[Math.floor(n / 2)];

  var getPercentile = function(sortedArr, p) {
    var idx = (sortedArr.length - 1) * p;
    var lower = Math.floor(idx);
    var upper = Math.ceil(idx);
    var weight = idx - lower;
    return sortedArr[lower] * (1 - weight) + sortedArr[upper] * weight;
  };

  var q1 = getPercentile(sortedLengths, 0.25);
  var q3 = getPercentile(sortedLengths, 0.75);
  var iqr = q3 - q1;

  // الانحراف المعياري
  var varianceSum = 0;
  for (var k = 0; k < lengths.length; k++) {
    varianceSum += Math.pow(lengths[k] - mean, 2);
  }
  var std = Math.sqrt(varianceSum / lengths.length);

  // حساب عتبة القيمة المتطرفة الدنيا ديناميكياً
  // المعادلة: Threshold = min(mean * 0.55, Q1 - 2.5 * IQR) مقيدة بين [2500, 5500]
  var rawThreshold = Math.min(mean * 0.55, q1 - 2.5 * iqr);
  var dynamicThreshold = Math.floor(Math.max(2500, Math.min(5500, rawThreshold)));

  // فحص الفصول المتطرفة
  var outliers = [];
  for (var m = 0; m < chapterRows.length; m++) {
    var ch = chapterRows[m];
    if (ch.length < dynamicThreshold) {
      outliers.push({
        row: ch.row,
        chapter_number: ch.chapter_num,
        suffix: ch.suffix,
        char_count: ch.length,
        deficit: dynamicThreshold - ch.length,
        novel_name: ch.novel
      });
    }
  }

  // ترتيب المتطرفين حسب رقم الفصل
  outliers.sort(function(a, b) { return a.chapter_number - b.chapter_number; });

  return {
    novel_name: novelName,
    total_chapters: chapterRows.length,
    stats: {
      count: chapterRows.length,
      mean_length: Math.round(mean * 10) / 10,
      median_length: Math.round(median * 10) / 10,
      std_dev: Math.round(std * 10) / 10,
      q1: Math.round(q1),
      q3: Math.round(q3),
      iqr: Math.round(iqr),
      calculated_raw_threshold: Math.round(rawThreshold),
      threshold_used: dynamicThreshold
    },
    outliers: outliers,
    total_outliers: outliers.length
  };
}

/**
 * تحديث محتوى الفصل مباشرة في نفس الخلية (العمود B) دون إتلاف الترتيب أو مس السطور الأخرى
 */
function updateChapterContentInPlace(spreadsheetId, sheetName, novelName, chapterNum, newContent) {
  var ssId = spreadsheetId || RAW_ARCHIVE_SPREADSHEET_ID;
  var ss = SpreadsheetApp.openById(ssId);
  var sheet = sheetName ? (ss.getSheetByName(sheetName) || ss.getSheets()[0]) : ss.getSheets()[0];
  var lastRow = sheet.getLastRow();

  if (lastRow <= 1) {
    return { success: false, error: "الجدول فارغ" };
  }

  var numCols = sheet.getLastColumn();
  var headers = sheet.getRange(1, 1, 1, numCols).getValues()[0];
  var colCfg = detectSheetColumns(sheet, headers);
  var targetKey = getChapterDeduplicationKey(novelName, chapterNum);

  var allData = sheet.getRange(2, 1, lastRow - 1, numCols).getValues();
  var foundRowIndex = -1;

  for (var i = 0; i < allData.length; i++) {
    var rowNovel = String(allData[i][colCfg.novelCol] || "").trim().toLowerCase();
    var rowChap = allData[i][colCfg.chapCol];
    var currentKey = getChapterDeduplicationKey(rowNovel, rowChap);

    if (currentKey === targetKey) {
      foundRowIndex = i;
      break;
    }
  }

  if (foundRowIndex === -1) {
    return { success: false, error: "الفصل غير موجود في الشيت", chapter: chapterNum };
  }

  var actualSheetRow = foundRowIndex + 2; // +2 لأن البيانات تبدأ من السطر 2
  var oldContent = String(allData[foundRowIndex][colCfg.contentCol] || "");

  // التحقق من أن المحتوى الجديد أطول أو ذو فائدة
  if (newContent.length < oldContent.length && oldContent.length >= 2500) {
    return {
      success: false,
      skipped: true,
      reason: "المحتوى الموجود أطول من المحتوى الجديد المُراد استبداله",
      old_length: oldContent.length,
      new_length: newContent.length,
      row: actualSheetRow,
      chapter: chapterNum
    };
  }

  // تحديث الخلية في نفس العمود (colCfg.contentCol + 1)
  sheet.getRange(actualSheetRow, colCfg.contentCol + 1).setValue(newContent);

  // تحديث عمود تاريخ الإنشاء/التعديل إذا وجد (العمود 4)
  if (numCols >= 4) {
    sheet.getRange(actualSheetRow, 4).setValue(new Date().toISOString());
  }

  SpreadsheetApp.flush();

  return {
    success: true,
    status: "updated_in_place_column_b",
    row: actualSheetRow,
    chapter: chapterNum,
    old_length: oldContent.length,
    new_length: newContent.length,
    gain: newContent.length - oldContent.length
  };
}


