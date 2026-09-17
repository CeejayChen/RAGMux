<script setup lang="ts">
/**
 * 应用外壳：左侧知识库列表 + 右侧主内容区（参照 LightRAG WebUI 的布局）。
 */
import { Collection, DataAnalysis, Monitor } from '@element-plus/icons-vue'
import KBList from './components/KBList.vue'
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="sidebar-header">
        <div class="brand">
          <el-icon><collection /></el-icon> RAGMux
        </div>
        <div class="subtitle">LightRAG 多知识库管理</div>
      </div>

      <KBList />

      <div class="sidebar-footer">
        <router-link to="/profiles" v-slot="{ navigate, isActive }">
          <button class="nav-link" :class="{ on: isActive }" @click="navigate">
            <el-icon><data-analysis /></el-icon> 模型配置
          </button>
        </router-link>
        <router-link to="/overview" v-slot="{ navigate, isActive }">
          <button class="nav-link" :class="{ on: isActive }" @click="navigate">
            <el-icon><monitor /></el-icon> 系统概览
          </button>
        </router-link>
      </div>
    </aside>
    <main class="main-area">
      <router-view />
    </main>
  </div>
</template>
