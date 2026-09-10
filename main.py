#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
سكربت اتصال مباشر بمنصة Pocket Option
الغرض: اختبار الاتصال وسحب الرصيد فقط.
"""

import os
import sys
import time
import traceback

# ============================================================
# 1) المفتاح (SESSION) الذي قدمته — يمكن استبداله بمتغير بيئة
# ============================================================
SESSION = '42["auth",{"session":"vtftn12e6f5f5008moitsd6skl","isDemo":1,"uid":27658142,"platform":2,"isFastHistory":true,"isOptimized":true}]'
SESSION = os.environ.get("POCKET_SESSION", SESSION)

# ============================================================
# 2) استيراد المكتبة (تدعم عدة أسماء)
# ============================================================
LIB_TYPE = "none"
PocketOption = None

try:
    from pocketoptionapi.stable_api import PocketOption
    LIB_TYPE = "pocketoptionapi"
except ImportError:
    try:
        from pocketoptionapi2.stable_api import PocketOption
        LIB_TYPE = "pocketoptionapi2"
    except ImportError:
        try:
            from pocket_option import PocketOptionClient, AuthorizationData
            LIB_TYPE = "pocket_option"
        except ImportError:
            LIB_TYPE = "none"


def main():
    print("=" * 60)
    print(f"🔌 نوع المكتبة المكتشفة: {LIB_TYPE}")
    print("=" * 60)

    if LIB_TYPE == "none":
        print("❌ لم يتم العثور على أي مكتبة PocketOption مثبتة.")
        print("   ثبّت المكتبة بالأمر:")
        print("   pip install git+https://github.com/Mastaaa1987/PocketOptionAPI-v2.git")
        print("   أو:")
        print("   pip install pocketoptionapi2")
        sys.exit(1)

    # --------------------------------------------------------
    # 3) الاتصال بالمنصة
    # --------------------------------------------------------
    try:
        if LIB_TYPE in ("pocketoptionapi", "pocketoptionapi2"):
            # المكتبة القديمة/الجديدة تطلب كائن PocketOption مع وضع Demo
            api = PocketOption(demo=True)  # True = حساب تجريبي

            # تمرير الجلسة (session) — بعض الإصدارات تطلبها في connect()
            try:
                # الطريقة الشائعة في pocketoptionapi-v2
                api.connect(session=SESSION)
            except TypeError:
                # إذا لم يقبل session كوسيط، نجرب set_session ثم connect
                try:
                    api.set_session(SESSION)
                    api.connect()
                except Exception:
                    # محاولة أخيرة: تمرير المفتاح في المنشئ (بعض الإصدارات القديمة)
                    api = PocketOption(SESSION, demo=True)
                    api.connect()

        elif LIB_TYPE == "pocket_option":
            # المكتبة غير المتزامنة (async) — سنشرحها في ملاحظة أسفل السكربت
            print("⚠️ المكتبة المكتشفة 'pocket_option' غير متزامنة (async).")
            print("   هذا السكربت يدعم المكتبات المتزامنة فقط (pocketoptionapi).")
            sys.exit(1)

        print("✅ تم استدعاء connect() بنجاح. جاري الانتظار 5 ثوانٍ لاستقرار الاتصال...")
        time.sleep(5)

    except Exception as e:
        print("\n❌ فشل الاتصال:")
        print(f"   الخطأ: {e}")
        print("\n📋 تتبع المكدس الكامل:")
        traceback.print_exc()
        sys.exit(1)

    # --------------------------------------------------------
    # 4) سحب الرصيد للتأكد من نجاح الاتصال
    # --------------------------------------------------------
    try:
        balance = api.GetBalance()
        print(f"\n💰 الرصيد الحالي (الحساب التجريبي): {balance}")
    except AttributeError:
        try:
            balance = api.get_balance()
            print(f"\n💰 الرصيد الحالي (الحساب التجريبي): {balance}")
        except Exception as e:
            print(f"\n⚠️ لم نتمكن من سحب الرصيد: {e}")
            print("   لكن الاتصال قد يكون ناجحًا. تحقق يدويًا من المنصة.")
    except Exception as e:
        print(f"\n⚠️ خطأ أثناء سحب الرصيد: {e}")

    # --------------------------------------------------------
    # 5) (اختياري) جلب قائمة الأصول
    # --------------------------------------------------------
    try:
        pairs = api.GetPairs()
        print(f"\n📊 عدد الأصول المتاحة: {len(pairs) if pairs else 0}")
        if pairs:
            print("   أول 5 أصول:", list(pairs)[:5])
    except Exception:
        print("\nℹ️ لا يمكن جلب قائمة الأصول (قد لا تدعمها هذه النسخة).")

    print("\n" + "=" * 60)
    print("✅ انتهى السكربت.")
    print("=" * 60)


if __name__ == "__main__":
    main()
