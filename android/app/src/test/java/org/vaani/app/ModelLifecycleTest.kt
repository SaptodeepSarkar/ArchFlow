package org.vaani.app
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test
import java.util.concurrent.atomic.AtomicInteger
class ModelLifecycleTest {
 @Test fun economy_releases_on_success_failure_and_cancel() = runBlocking {
  val released=AtomicInteger();val model=LazyModel<Int> {released.incrementAndGet()}
  assertEquals(7,model.use("one",0,{7}) {it})
  try {model.use("one",0,{7}) {error("inference")}} catch(_: IllegalStateException) { }
  val entered=CompletableDeferred<Unit>();val job=launch {model.use("one",0,{7}) {entered.complete(Unit);awaitCancellation()}}
  entered.await();job.cancelAndJoin();assertEquals(3,released.get());model.clear();assertEquals(3,released.get())
 }
 @Test fun retained_load_is_shared_and_unload_waits_for_operation() = runBlocking {
  val loaded=AtomicInteger();val released=AtomicInteger();val model=LazyModel<Int> {released.incrementAndGet()}
  val entered=CompletableDeferred<Unit>();val finish=CompletableDeferred<Unit>()
  val active=async {model.use("one",1000,{loaded.incrementAndGet()}) {entered.complete(Unit);finish.await();it}}
  entered.await();val unload=launch {model.clear()};yield();assertEquals(0,released.get())
  finish.complete(Unit);active.await();unload.join();assertEquals(1,released.get())
  model.use("two",1000,{loaded.incrementAndGet()}) {it};model.use("two",1000,{loaded.incrementAndGet()}) {it}
  assertEquals(2,loaded.get());delay(1200);assertEquals(2,released.get())
 }
}
