package com.basaltfocus.app

import android.app.Application
import androidx.room.Room
import com.basaltfocus.app.data.HistoryDatabase
import com.basaltfocus.app.data.Repository

class BasaltApplication : Application() {
    val repository: Repository by lazy {
        Repository(this, Room.databaseBuilder(this, HistoryDatabase::class.java, "basalt-history").build())
    }
}
