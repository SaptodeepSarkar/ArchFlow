package org.vaani.app.features
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import org.vaani.app.*
@Composable fun PersonalizationScreen(){
 val context=LocalContext.current;val store=remember {PersonalizationStore(context)};var snapshot by remember {mutableStateOf(store.snapshot())};var kind by remember {mutableStateOf("Vocabulary")};var first by remember {mutableStateOf("")};var second by remember {mutableStateOf("")};var message by remember {mutableStateOf("")}
 Column(Modifier.verticalScroll(rememberScrollState()),verticalArrangement=Arrangement.spacedBy(12.dp)){
  Text("Your words",style=MaterialTheme.typography.headlineMedium);Text("Vocabulary, snippets, links and replacements are saved encrypted on this device.")
  Row {listOf("Vocabulary","Snippet","Replacement").forEach {type->FilterChip(selected=kind==type,onClick={kind=type},label={Text(type)})}}
  OutlinedTextField(value=first,onValueChange={first=it},label={Text(if(kind=="Vocabulary")"Spelling" else "Spoken trigger")},singleLine=true)
  OutlinedTextField(value=second,onValueChange={second=it},label={Text(if(kind=="Vocabulary")"Heard as (optional)" else "Text or link")})
  Button(onClick={runCatching {when(kind){"Vocabulary"->store.addVocabulary(first,second);"Snippet"->store.addSnippet(first,second);else->store.addReplacement(first,second)};snapshot=store.snapshot();first="";second="";message="Saved"}.onFailure {message="Check the value lengths and try again"}}){Text("Add")}
  Text(message)
  snapshot.vocabulary.forEach {value->Row {Text(value.canonical,Modifier.weight(1f));TextButton(onClick={store.removeVocabulary(value.id);snapshot=store.snapshot()}){Text("Remove")}}}
  snapshot.snippets.forEach {value->Row {Text("${value.trigger}: ${value.value}",Modifier.weight(1f));TextButton(onClick={store.removeSnippet(value.id);snapshot=store.snapshot()}){Text("Remove")}}}
  snapshot.replacements.forEach {value->Row {Text("${value.source}: ${value.target}",Modifier.weight(1f));TextButton(onClick={store.removeReplacement(value.id);snapshot=store.snapshot()}){Text("Remove")}}}
 }
}
