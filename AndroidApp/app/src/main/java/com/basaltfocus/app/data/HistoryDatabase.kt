package com.basaltfocus.app.data

import androidx.room.Dao
import androidx.room.Database
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.RoomDatabase
import kotlinx.coroutines.flow.Flow

@Dao
interface HistoryDao {
    @Query("SELECT * FROM sprints ORDER BY startedAt DESC, id DESC")
    fun observe(): Flow<List<SprintRecord>>

    @Query("SELECT * FROM sprints WHERE id = :id")
    suspend fun find(id: String): SprintRecord?

    @Query("SELECT momentumAfter FROM sprints ORDER BY startedAt DESC, id DESC LIMIT 1")
    suspend fun latestMomentum(): Double?

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insert(record: SprintRecord)

    @Query("UPDATE sprints SET journal = :line WHERE id = :id")
    suspend fun journal(id: String, line: String)
}

@Database(entities = [SprintRecord::class], version = 1, exportSchema = true)
abstract class HistoryDatabase : RoomDatabase() {
    abstract fun history(): HistoryDao
}
