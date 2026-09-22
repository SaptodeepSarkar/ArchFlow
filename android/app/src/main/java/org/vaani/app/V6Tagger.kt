package org.vaani.app

import org.bouncycastle.crypto.digests.Blake2bDigest
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** CPU-only reader and inference for the shared V6 hashed tagger package. */
internal class V6Tagger private constructor(private val tensors: Map<String, Tensor>) {
    data class Prediction(val tokenLabels: IntArray, val punctuation: IntArray)
    private data class Tensor(val dims: IntArray, val bytes: ByteArray)

    fun predict(tokens: List<String>): Prediction {
        val embedding = floats("embedding.weight", 2048 * 96)
        val bodyW = floats("body.0.weight", 96 * 96)
        val bodyB = floats("body.0.bias", 96)
        val tokenW = floats("token.weight", 6 * 96)
        val tokenB = floats("token.bias", 6)
        val punctW = floats("punct.weight", 7 * 96)
        val punctB = floats("punct.bias", 7)
        val token = IntArray(tokens.size)
        val punct = IntArray(tokens.size)
        tokens.indices.forEach { index ->
            val hidden = FloatArray(96)
            featureIds(tokens, index).forEach { bucket -> repeat(96) { col -> hidden[col] += embedding[bucket * 96 + col] } }
            val body = FloatArray(96) { row ->
                var value = bodyB[row]
                repeat(96) { col -> value += bodyW[row * 96 + col] * hidden[col] }
                value.coerceAtLeast(0f)
            }
            token[index] = argmax(linear(tokenW, tokenB, body, 6))
            punct[index] = argmax(linear(punctW, punctB, body, 7))
        }
        return Prediction(token, punct)
    }

    private fun floats(name: String, count: Int): FloatArray {
        val tensor = tensors[name] ?: error("missing V6 tensor $name")
        require(tensor.bytes.size == count * 4) { "invalid V6 tensor $name" }
        return FloatArray(count) { ByteBuffer.wrap(tensor.bytes, it * 4, 4).order(ByteOrder.LITTLE_ENDIAN).float }
    }

    companion object {
        private val MAGIC = byteArrayOf(0x56, 0x36, 0x54, 0x47, 1, 0, 0, 0)

        fun load(bytes: ByteArray): V6Tagger {
            val reader = Reader(bytes)
            require(reader.take(8).contentEquals(MAGIC)) { "bad V6TG magic" }
            val count = reader.u32()
            require(count in 1..64) { "invalid V6 tensor count" }
            val tensors = linkedMapOf<String, Tensor>()
            repeat(count) {
                val name = reader.take(reader.u32()).toString(Charsets.UTF_8)
                require(name !in tensors) { "duplicate V6 tensor" }
                val rank = reader.u32()
                require(rank <= 4) { "invalid V6 tensor rank" }
                val dims = IntArray(rank) { reader.u32() }.also { require(it.all { dim -> dim > 0 }) }
                val elements = dims.fold(1L) { total, dim -> total * dim }.also { require(it <= Int.MAX_VALUE) }
                tensors[name] = Tensor(dims, reader.take(Math.multiplyExact(elements.toInt(), 4)))
            }
            require(reader.done()) { "trailing V6 package bytes" }
            return V6Tagger(tensors)
        }

        private fun featureIds(tokens: List<String>, index: Int): List<Int> {
            val lower = tokens[index].lowercase()
            val units = mutableListOf("tok=$lower", "pos=${index.coerceAtMost(7)}", "len=${lower.length.coerceAtMost(12)}")
            if (index > 0) units += "prev=${tokens[index - 1].lowercase()}"
            if (index + 1 < tokens.size) units += "next=${tokens[index + 1].lowercase()}"
            for (j in 0 until (lower.length - 2).coerceAtLeast(0)) units += "c3=${lower.substring(j, j + 3)}"
            return units.take(10).map(::hashId)
        }

        private fun hashId(value: String): Int {
            // The Python trainer uses hashlib.blake2b(digest_size=4), i.e.
            // a 32-bit BLAKE2b digest (the constructor takes bits).
            val digest = Blake2bDigest(32)
            val input = value.toByteArray()
            digest.update(input, 0, input.size)
            val out = ByteArray(4)
            digest.doFinal(out, 0)
            return ByteBuffer.wrap(out).order(ByteOrder.LITTLE_ENDIAN).int.toUInt().toInt() % 2048
        }

        private fun linear(weights: FloatArray, bias: FloatArray, input: FloatArray, output: Int) = FloatArray(output) { row ->
            bias[row] + input.indices.sumOf { col -> (weights[row * input.size + col] * input[col]).toDouble() }.toFloat()
        }

        private fun argmax(values: FloatArray) = values.indices.maxByOrNull { values[it] } ?: 0
    }

    private class Reader(private val bytes: ByteArray) {
        private var offset = 0
        fun take(size: Int): ByteArray = bytes.copyOfRange(offset, (offset + size).also { require(size >= 0 && it <= bytes.size) }).also { offset += size }
        fun u32() = ByteBuffer.wrap(take(4)).order(ByteOrder.LITTLE_ENDIAN).int
        fun done() = offset == bytes.size
    }
}
