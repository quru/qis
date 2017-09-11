#!/bin/bash -v

# TODO combine helpers with image viewers before minimising
#
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/admin/static/js/admin.min.js imageserver/admin/static/js/admin.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/reports/static/js/chart.min.js imageserver/reports/static/js/chart.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/reports/static/js/lib/mooflot.min.js imageserver/reports/static/js/lib/mooflot.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/reports/static/js/system_stats.min.js imageserver/reports/static/js/system_stats.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/account_edit.min.js imageserver/static/js/account_edit.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/base.min.js imageserver/static/js/base.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/canvas_view.min.js imageserver/static/js/canvas_view.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/details.min.js imageserver/static/js/details.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/details_edit.min.js imageserver/static/js/details_edit.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/excanvas.min.js imageserver/static/js/excanvas.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/gallery_view.min.js imageserver/static/js/gallery_view.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/lib/lassocrop.min.js imageserver/static/js/lib/lassocrop.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/lib/picker.min.js imageserver/static/js/lib/picker.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/list.min.js imageserver/static/js/list.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/preview_popup.min.js imageserver/static/js/preview_popup.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/publish.min.js imageserver/static/js/publish.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/simple_view.min.js imageserver/static/js/simple_view.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/slideshow_view.min.js imageserver/static/js/slideshow_view.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/upload.min.js imageserver/static/js/upload.js
