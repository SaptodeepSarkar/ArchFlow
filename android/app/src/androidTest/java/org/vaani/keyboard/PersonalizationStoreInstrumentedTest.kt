package org.vaani.keyboard

import android.content.Context
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PersonalizationStoreInstrumentedTest {
    private lateinit var context: Context
    private lateinit var store: PersonalizationStore

    @Before
    fun resetStore() {
        context = InstrumentationRegistry.getInstrumentation().targetContext
        context.deleteDatabase("vaani_personalization.db")
        context.getSharedPreferences("vaani_personalization", Context.MODE_PRIVATE).edit().clear().commit()
        store = PersonalizationStore(context)
    }

    @Test
    fun vocabularyAliasesRoundTripAndRenderRulesRemainDeterministic() {
        assertTrue(store.addVocabulary("Hyprland", listOf("hyper land", " hyperland ")))
        assertEquals(listOf("hyper land", "hyperland"), store.vocabulary().single().spokenAliases)
        assertTrue(store.addSnippet("my GitHub", "https://github.com/example/repo"))
        assertTrue(store.addReplacement("sapto deep", "Saptodeep"))
        assertEquals("send https://github.com/example/repo to Saptodeep about Hyprland", store.render("send my github to sapto deep about hyper land"))
    }

    @Test
    fun remoteTombstoneHidesEntryButRemainsSyncVisible() {
        assertTrue(store.addSnippet("my email", "user@example.com"))
        val entry = store.snippets().single()
        store.remove(PersonalizationStore.Kind.SNIPPET, entry.id)
        assertTrue(store.snippets().isEmpty())
        assertEquals(entry.id, store.syncEntries(PersonalizationStore.Kind.SNIPPET).single().id)
        assertTrue(store.syncEntries(PersonalizationStore.Kind.SNIPPET).single().deletedAtMs != null)
    }
}
