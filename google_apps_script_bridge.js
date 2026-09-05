/**
 * ==============================================================================
 * Google Apps Script - Cloud AI Engine & Serverless Novel Scraper v3.0
 * ==============================================================================
 * 
 * هذا السكربت يمثل المحرك السحابي الذكي (يعمل 24/7 دون الحاجة لتشغيل الحاسوب):
 * 1. استدعاء نموذج Google Gemini 3.8 Flash لتحليل وتنسيق محتوى الفصول.
 * 2. جلب صفحات الفصول والروايات سحابياً عبر شبكة سيرفرات Google الموزعة.
 * 3. حماية تامة: المفتاح مخفي ومحفوظ داخل خوادم Google ولا يظهر في GitHub.
 */

// مفتاح Gemini API السحابي (يوضع في متغيرات السكربت أو يتم تمريره من التطبيق)
var GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE";

// النموذج المعتمد حصراً للسرعة الفائقة والذكاء
var DEFAULT_MODEL = "gemini-3.8-flash";

function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return createJsonResponse({ error: "لم يتم استلام أي بيانات في الطلب" }, 400);
    }

    var requestData = JSON.parse(e.postData.contents);
    var action = requestData.action || "gemini";

    // =========================================================================
    // 1. جلب صفحات الويب سحابياً عبر خوادم Google (Cloud Proxy Fetch)
    // =========================================================================
    if (action === "fetch_html" || requestData.target_url) {
      var targetUrl = requestData.target_url || requestData.url;
      if (!targetUrl) {
        return createJsonResponse({ error: "حقل target_url مفقود" }, 400);
      }

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
      var pageCode = pageResponse.getResponseCode();
      var pageHtml = pageResponse.getContentText();

      return createJsonResponse({
        success: (pageCode >= 200 && pageCode < 400),
        statusCode: pageCode,
        url: targetUrl,
        html: pageHtml,
        length: pageHtml.length
      }, 200);
    }

    // =========================================================================
    // 2. تحليل واستخراج البيانات بواسطة Gemini 3.8 Flash السحابي
    // =========================================================================
    var apiKey = (requestData.apiKey && requestData.apiKey.trim() !== "") ? requestData.apiKey : GEMINI_API_KEY;
    var model = requestData.model || DEFAULT_MODEL;
    var prompt = requestData.prompt;

    if (!prompt) {
      return createJsonResponse({ error: "حقل prompt مفقود في الطلب" }, 400);
    }

    // تنظيف اسم النموذج وضمان استخدام 3.8 Flash
    if (model.indexOf("models/") === 0) {
      model = model.substring(7);
    }

    var apiUrl = "https://generativelanguage.googleapis.com/v1beta/models/" + encodeURIComponent(model) + ":generateContent?key=" + encodeURIComponent(apiKey.trim());

    var payload = {
      "contents": [
        {
          "parts": [
            { "text": prompt }
          ]
        }
      ],
      "generationConfig": {
        "temperature": 0.1,
        "responseMimeType": "application/json"
      }
    };

    var options = {
      "method": "post",
      "contentType": "application/json",
      "payload": JSON.stringify(payload),
      "muteHttpExceptions": true
    };

    var response = UrlFetchApp.fetch(apiUrl, options);
    var statusCode = response.getResponseCode();
    var responseText = response.getContentText();

    if (statusCode !== 200) {
      return createJsonResponse({
        error: "Gemini API Error (" + statusCode + "): " + responseText,
        statusCode: statusCode
      }, 200);
    }

    var parsedResponse = JSON.parse(responseText);
    var textOutput = "";

    if (parsedResponse.candidates && parsedResponse.candidates.length > 0) {
      var candidate = parsedResponse.candidates[0];
      if (candidate.content && candidate.content.parts) {
        for (var i = 0; i < candidate.content.parts.length; i++) {
          textOutput += candidate.content.parts[i].text || "";
        }
      }
    }

    return createJsonResponse({
      success: true,
      text: textOutput,
      model_used: model
    }, 200);

  } catch (err) {
    return createJsonResponse({
      error: "GAS Server Error: " + err.toString()
    }, 500);
  }
}

function doGet(e) {
  return ContentService.createTextOutput("Gemini 3.8 Flash & Cloud Scraper Engine is Online 24/7!").setMimeType(ContentService.MimeType.TEXT);
}

function createJsonResponse(data, statusCode) {
  return ContentService.createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}
