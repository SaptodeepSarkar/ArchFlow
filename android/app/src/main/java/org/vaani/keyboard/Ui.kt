package org.vaani.keyboard

import android.content.Context
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.widget.*

class Ui(private val context: Context) {
    companion object {
        val ink = 0xff20251f.toInt()
        val paper = 0xfff7f6ef.toInt()
        val lime = 0xffd7f36f.toInt()
    }
    fun dp(n: Int) = (n * context.resources.displayMetrics.density).toInt()
    fun column() = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL; setPadding(dp(24), dp(28), dp(24), dp(28)); setBackgroundColor(paper)
    }
    fun label(value: String, size: Float = 16f) = TextView(context).apply {
        text = value; textSize = size; setTextColor(ink); setPadding(0, dp(8), 0, dp(12))
    }
    fun title(value: String, size: Float = 32f) = label(value, size).apply {
        typeface = Typeface.create("serif", Typeface.NORMAL); setPadding(0, dp(22), 0, dp(8))
    }
    fun button(value: String, click: () -> Unit) = Button(context).apply {
        text = value; textSize = 16f; isAllCaps = false; setTextColor(ink)
        minHeight = dp(52); minimumHeight = dp(52); setPadding(dp(12), dp(10), dp(12), dp(10))
        background = GradientDrawable().apply { setColor(lime); cornerRadius = dp(16).toFloat() }
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(8); bottomMargin = dp(4) }
        setOnClickListener { click() }
    }
}

