import { createRouter, createWebHistory } from 'vue-router'
import { auth, loadSession } from './stores/auth'
import AppShell from './components/AppShell.vue'

export const router = createRouter({ history: createWebHistory(), routes: [
  { path: '/login', component: () => import('./views/Login.vue') },
  { path: '/change-password', component: () => import('./views/ChangePassword.vue') },
  { path: '/', component: AppShell, children: [
    { path: '', component: () => import('./views/Dashboard.vue'), meta: { title: '运行概览' } },
    { path: 'nodes', component: () => import('./views/Nodes.vue'), meta: { title: '节点管理' } },
    { path: 'tasks', component: () => import('./views/Tasks.vue'), meta: { title: '任务记录' } },
    { path: 'events', component: () => import('./views/Events.vue'), meta: { title: '事件日志' } },
    { path: 'settings', component: () => import('./views/Settings.vue'), meta: { title: '控制台设置' } },
  ] },
  { path: '/:pathMatch(.*)*', redirect: '/' },
] })
router.beforeEach(async to => {
  await loadSession()
  if (!auth.authenticated && to.path !== '/login') return '/login'
  if (auth.authenticated && auth.must_change_password && to.path !== '/change-password') return '/change-password'
  if (auth.authenticated && !auth.must_change_password && ['/login', '/change-password'].includes(to.path)) return '/'
})
