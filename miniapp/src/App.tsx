import { Navigate, Route, Routes } from 'react-router-dom'
import { MainLayout } from './components/layout/MainLayout'
import { GroupsPage } from './pages/GroupsPage'
import { NoteEditorPage } from './pages/NoteEditorPage'
import { NotesListPage } from './pages/NotesListPage'
import { AgentPage } from './pages/AgentPage'
import { SettingsPage } from './pages/SettingsPage'

const App = () => (
  <Routes>
    <Route element={<MainLayout />}>
      <Route index element={<NotesListPage />} />
      <Route path="assistant" element={<AgentPage />} />
      <Route path="groups" element={<GroupsPage />} />
      <Route path="settings" element={<SettingsPage />} />
      <Route path="notes/new" element={<NoteEditorPage mode="create" />} />
      <Route path="notes/:noteId" element={<NoteEditorPage mode="edit" />} />
    </Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>
)

export default App
