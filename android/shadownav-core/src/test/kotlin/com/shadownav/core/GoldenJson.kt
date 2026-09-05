package com.shadownav.core

/**
 * A tiny JSON reader for the golden vectors.
 *
 * Deliberately dependency-free: adding a JSON library to the module whose whole
 * purpose is to be a minimal, auditable port would be the wrong trade. The
 * golden files are machine-generated with a known shape, so this only needs to
 * handle objects, arrays, numbers, strings and booleans.
 */
object GoldenJson {

    fun parse(text: String): Any? = Parser(text).run {
        skipWhitespace()
        val v = parseValue()
        skipWhitespace()
        v
    }

    fun load(name: String): Map<*, *> {
        val stream = GoldenJson::class.java.getResourceAsStream("/golden/$name.json")
            ?: error(
                "missing golden/$name.json -- regenerate with " +
                    "`PYTHONPATH=. python scripts/export_golden.py` in python/"
            )
        return parse(stream.bufferedReader().readText()) as Map<*, *>
    }

    // -- typed accessors -------------------------------------------------

    fun Map<*, *>.num(key: String): Double = (this[key] as Number).toDouble()

    fun Map<*, *>.int(key: String): Int = (this[key] as Number).toInt()

    fun Map<*, *>.bool(key: String): Boolean = this[key] as Boolean

    fun Map<*, *>.obj(key: String): Map<*, *> = this[key] as Map<*, *>

    fun Map<*, *>.arr(key: String): List<*> = this[key] as List<*>

    fun Map<*, *>.doubles(key: String): DoubleArray =
        (this[key] as List<*>).map { (it as Number).toDouble() }.toDoubleArray()

    fun Map<*, *>.matrix(key: String): Array<DoubleArray> =
        (this[key] as List<*>).map { row ->
            (row as List<*>).map { (it as Number).toDouble() }.toDoubleArray()
        }.toTypedArray()

    private class Parser(private val s: String) {
        private var i = 0

        fun skipWhitespace() {
            while (i < s.length && s[i].isWhitespace()) i++
        }

        fun parseValue(): Any? {
            skipWhitespace()
            return when (s[i]) {
                '{' -> parseObject()
                '[' -> parseArray()
                '"' -> parseString()
                't' -> { i += 4; true }
                'f' -> { i += 5; false }
                'n' -> { i += 4; null }
                else -> parseNumber()
            }
        }

        private fun parseObject(): Map<String, Any?> {
            val out = LinkedHashMap<String, Any?>()
            i++ // {
            skipWhitespace()
            if (s[i] == '}') { i++; return out }
            while (true) {
                skipWhitespace()
                val key = parseString()
                skipWhitespace()
                i++ // :
                out[key] = parseValue()
                skipWhitespace()
                when (s[i]) {
                    ',' -> i++
                    '}' -> { i++; return out }
                    else -> error("expected , or } at $i")
                }
            }
        }

        private fun parseArray(): List<Any?> {
            val out = ArrayList<Any?>()
            i++ // [
            skipWhitespace()
            if (s[i] == ']') { i++; return out }
            while (true) {
                out.add(parseValue())
                skipWhitespace()
                when (s[i]) {
                    ',' -> i++
                    ']' -> { i++; return out }
                    else -> error("expected , or ] at $i")
                }
            }
        }

        private fun parseString(): String {
            i++ // opening quote
            val sb = StringBuilder()
            while (s[i] != '"') {
                if (s[i] == '\\') {
                    i++
                    when (s[i]) {
                        'n' -> sb.append('\n')
                        't' -> sb.append('\t')
                        'r' -> sb.append('\r')
                        'b' -> sb.append('\b')
                        'u' -> {
                            sb.append(s.substring(i + 1, i + 5).toInt(16).toChar())
                            i += 4
                        }
                        else -> sb.append(s[i])
                    }
                } else {
                    sb.append(s[i])
                }
                i++
            }
            i++ // closing quote
            return sb.toString()
        }

        private fun parseNumber(): Double {
            val start = i
            while (i < s.length && (s[i].isDigit() || s[i] in "+-.eE")) i++
            return s.substring(start, i).toDouble()
        }
    }
}
