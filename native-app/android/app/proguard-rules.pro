# JNA و کد اتصال UniFFI با reflection کار می کنند؛ نباید کوچک یا حذف شوند
-keep class com.sun.jna.** { *; }
-keep class * implements com.sun.jna.** { *; }
-keep class dezhcode.asotas.core.** { *; }
-dontwarn java.awt.**
