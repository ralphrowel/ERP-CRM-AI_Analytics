import React, { useEffect, useState } from 'react'
import {
  Building,
  CheckCircle,
  Edit2,
  FolderPlus,
  Plus,
  RefreshCw,
  UserX,
} from 'lucide-react'
import { ApiError } from '../api/client'
import {
  type Department,
  type Employee,
  type EmployeeCreatePayload,
  employeesApi,
  type EmployeeUpdatePayload,
} from '../api/employees'
import { ConflictAlert } from '../components/ConflictAlert'
import { Modal } from '../components/Modal'
import { ProblemAlert } from '../components/ProblemAlert'

export const EmployeesPage: React.FC = () => {
  const [employees, setEmployees] = useState<Employee[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(15)
  const [selectedDeptId, setSelectedDeptId] = useState<number | undefined>(undefined)
  const [isLoading, setIsLoading] = useState(true)

  // Errors & Conflict
  const [conflictError, setConflictError] = useState<string | null>(null)
  const [generalError, setGeneralError] = useState<ApiError | Error | null>(null)

  // Modals
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [isEditOpen, setIsEditOpen] = useState(false)
  const [isDeptModalOpen, setIsDeptModalOpen] = useState(false)
  const [selectedEmployee, setSelectedEmployee] = useState<Employee | null>(null)

  // Forms
  const [formData, setFormData] = useState<EmployeeCreatePayload>({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    department_id: 1,
    job_title: '',
    hire_date: new Date().toISOString().split('T')[0],
  })

  const [editFormData, setEditFormData] = useState<EmployeeUpdatePayload>({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    department_id: 1,
    job_title: '',
    hire_date: '',
    version: 1,
  })

  const [newDeptCode, setNewDeptCode] = useState('')
  const [newDeptName, setNewDeptName] = useState('')

  const loadData = async () => {
    setIsLoading(true)
    setConflictError(null)
    setGeneralError(null)
    try {
      const [empRes, deptRes] = await Promise.all([
        employeesApi.list({
          page,
          page_size: pageSize,
          department_id: selectedDeptId,
        }),
        employeesApi.listDepartments(),
      ])
      setEmployees(empRes.items)
      setTotal(empRes.total)
      setDepartments(deptRes)
      if (deptRes.length > 0 && formData.department_id === 1) {
        setFormData((prev) => ({ ...prev, department_id: deptRes[0].id }))
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) setGeneralError(err)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [page, selectedDeptId])

  const handleCreateEmployee = async (e: React.FormEvent) => {
    e.preventDefault()
    setGeneralError(null)
    try {
      await employeesApi.create(formData)
      setIsCreateOpen(false)
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError) setGeneralError(err)
    }
  }

  const openEditModal = (emp: Employee) => {
    setSelectedEmployee(emp)
    setConflictError(null)
    setGeneralError(null)
    setEditFormData({
      first_name: emp.first_name,
      last_name: emp.last_name,
      email: emp.email || '',
      phone: emp.phone || '',
      department_id: emp.department_id,
      job_title: emp.job_title || '',
      hire_date: emp.hire_date,
      version: emp.version,
    })
    setIsEditOpen(true)
  }

  const handleUpdateEmployee = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedEmployee) return
    setConflictError(null)
    setGeneralError(null)

    try {
      await employeesApi.update(selectedEmployee.id, editFormData)
      setIsEditOpen(false)
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.isConflict) {
          setConflictError(
            'This employee record was modified by another session. Please reload to see updated details.'
          )
        } else {
          setGeneralError(err)
        }
      }
    }
  }

  const handleCreateDepartment = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newDeptCode.trim() || !newDeptName.trim()) return
    try {
      await employeesApi.createDepartment(newDeptCode.trim().toUpperCase(), newDeptName.trim())
      setNewDeptCode('')
      setNewDeptName('')
      setIsDeptModalOpen(false)
      const depts = await employeesApi.listDepartments()
      setDepartments(depts)
    } catch (err: unknown) {
      if (err instanceof ApiError) setGeneralError(err)
    }
  }

  const handleDeactivate = async (id: number) => {
    if (!confirm('Are you sure you want to deactivate this employee?')) return
    try {
      await employeesApi.deactivate(id)
      loadData()
    } catch (err: unknown) {
      if (err instanceof ApiError) setGeneralError(err)
    }
  }

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 800, color: '#f8fafc' }}>
            Employees & Organization
          </h1>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            Staff directory, internal departments, sequential employee numbers (EMP-0001), and job roles.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button
            onClick={() => setIsDeptModalOpen(true)}
            className="btn btn-secondary"
          >
            <FolderPlus size={16} /> New Department
          </button>
          <button
            id="btn-create-employee"
            onClick={() => setIsCreateOpen(true)}
            className="btn btn-primary"
          >
            <Plus size={16} /> New Employee
          </button>
        </div>
      </div>

      {conflictError && <ConflictAlert onReload={loadData} message={conflictError} />}
      {generalError && <ProblemAlert error={generalError} onDismiss={() => setGeneralError(null)} />}

      {/* Filter Bar */}
      <div
        className="glass-panel"
        style={{
          padding: '1rem',
          display: 'flex',
          gap: '1rem',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '1.5rem',
        }}
      >
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>Filter Department:</span>
          <select
            value={selectedDeptId || ''}
            onChange={(e) => {
              setSelectedDeptId(e.target.value ? parseInt(e.target.value) : undefined)
              setPage(1)
            }}
            className="input-field"
            style={{ width: 'auto', padding: '0.4rem 0.75rem' }}
          >
            <option value="">All Departments</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.code} - {d.name}
              </option>
            ))}
          </select>
        </div>

        <button onClick={loadData} className="btn btn-secondary" title="Refresh">
          <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Table */}
      <div className="glass-panel erp-table-container">
        <table className="erp-table">
          <thead>
            <tr>
              <th>Employee No</th>
              <th>Full Name</th>
              <th>Department</th>
              <th>Job Title</th>
              <th>Email</th>
              <th>Hire Date</th>
              <th>Status</th>
              <th>Version</th>
              <th style={{ textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {employees.length === 0 ? (
              <tr>
                <td colSpan={9} style={{ textAlign: 'center', padding: '2.5rem', color: 'var(--text-dim)' }}>
                  {isLoading ? 'Loading staff records...' : 'No employees found.'}
                </td>
              </tr>
            ) : (
              employees.map((e) => {
                const dept = departments.find((d) => d.id === e.department_id)
                return (
                  <tr key={e.id}>
                    <td>
                      <span className="code-pill">{e.employee_no}</span>
                    </td>
                    <td>
                      <div style={{ fontWeight: 600 }}>{e.first_name} {e.last_name}</div>
                    </td>
                    <td>
                      <span className="badge badge-subtle">
                        <Building size={11} /> {dept?.code || '—'}
                      </span>
                    </td>
                    <td>{e.job_title || '—'}</td>
                    <td>
                      <div style={{ fontSize: '0.85rem' }}>{e.email || '—'}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>{e.phone || ''}</div>
                    </td>
                    <td style={{ fontSize: '0.825rem' }}>{e.hire_date}</td>
                    <td>
                      {e.is_active ? (
                        <span className="badge badge-emerald"><CheckCircle size={12} /> Active</span>
                      ) : (
                        <span className="badge badge-rose"><UserX size={12} /> Inactive</span>
                      )}
                    </td>
                    <td>
                      <span className="badge badge-subtle">v{e.version}</span>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', gap: '0.35rem' }}>
                        <button
                          onClick={() => openEditModal(e)}
                          className="btn btn-secondary"
                          style={{ padding: '0.35rem 0.65rem' }}
                          title="Edit Employee"
                        >
                          <Edit2 size={13} /> Edit
                        </button>
                        {e.is_active && (
                          <button
                            onClick={() => handleDeactivate(e.id)}
                            className="btn btn-danger"
                            style={{ padding: '0.35rem 0.65rem' }}
                            title="Deactivate"
                          >
                            <UserX size={13} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginTop: '1rem',
          fontSize: '0.85rem',
          color: 'var(--text-muted)',
        }}
      >
        <span>
          Showing {employees.length} of {total} staff members
        </span>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="btn btn-secondary"
            style={{ padding: '0.3rem 0.75rem', fontSize: '0.8rem' }}
          >
            Previous
          </button>
          <span style={{ padding: '0.3rem 0.5rem', alignSelf: 'center' }}>Page {page}</span>
          <button
            disabled={page * pageSize >= total}
            onClick={() => setPage((p) => p + 1)}
            className="btn btn-secondary"
            style={{ padding: '0.3rem 0.75rem', fontSize: '0.8rem' }}
          >
            Next
          </button>
        </div>
      </div>

      {/* Create Employee Modal */}
      <Modal isOpen={isCreateOpen} onClose={() => setIsCreateOpen(false)} title="New Employee Onboarding" maxWidth="560px">
        <form onSubmit={handleCreateEmployee} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>First Name *</label>
              <input
                type="text"
                required
                value={formData.first_name}
                onChange={(e) => setFormData({ ...formData, first_name: e.target.value })}
                className="input-field"
                placeholder="Juan"
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Last Name *</label>
              <input
                type="text"
                required
                value={formData.last_name}
                onChange={(e) => setFormData({ ...formData, last_name: e.target.value })}
                className="input-field"
                placeholder="Dela Cruz"
              />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Department *</label>
              <select
                value={formData.department_id}
                onChange={(e) => setFormData({ ...formData, department_id: parseInt(e.target.value) })}
                className="input-field"
              >
                {departments.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.code} - {d.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Job Title</label>
              <input
                type="text"
                value={formData.job_title}
                onChange={(e) => setFormData({ ...formData, job_title: e.target.value })}
                className="input-field"
                placeholder="Sales Representative"
              />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Email</label>
              <input
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                className="input-field"
                placeholder="juan@company.ph"
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Hire Date *</label>
              <input
                type="date"
                required
                value={formData.hire_date}
                onChange={(e) => setFormData({ ...formData, hire_date: e.target.value })}
                className="input-field"
              />
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem' }}>
            <button type="button" onClick={() => setIsCreateOpen(false)} className="btn btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn btn-primary">
              Enroll Employee
            </button>
          </div>
        </form>
      </Modal>

      {/* Edit Employee Modal */}
      <Modal isOpen={isEditOpen} onClose={() => setIsEditOpen(false)} title={`Edit Employee: ${selectedEmployee?.employee_no}`}>
        <form onSubmit={handleUpdateEmployee} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>First Name</label>
              <input
                type="text"
                required
                value={editFormData.first_name}
                onChange={(e) => setEditFormData({ ...editFormData, first_name: e.target.value })}
                className="input-field"
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Last Name</label>
              <input
                type="text"
                required
                value={editFormData.last_name}
                onChange={(e) => setEditFormData({ ...editFormData, last_name: e.target.value })}
                className="input-field"
              />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Department</label>
              <select
                value={editFormData.department_id}
                onChange={(e) => setEditFormData({ ...editFormData, department_id: parseInt(e.target.value) })}
                className="input-field"
              >
                {departments.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.code} - {d.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Job Title</label>
              <input
                type="text"
                value={editFormData.job_title}
                onChange={(e) => setEditFormData({ ...editFormData, job_title: e.target.value })}
                className="input-field"
              />
            </div>
          </div>

          <div
            style={{
              padding: '0.75rem',
              borderRadius: '8px',
              backgroundColor: 'rgba(0, 0, 0, 0.25)',
              border: '1px solid var(--border-subtle)',
              fontSize: '0.775rem',
              color: 'var(--text-dim)',
            }}
          >
            Optimistic lock token: <strong>version {editFormData.version}</strong>.
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem' }}>
            <button type="button" onClick={() => setIsEditOpen(false)} className="btn btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn btn-primary">
              Save Changes
            </button>
          </div>
        </form>
      </Modal>

      {/* New Department Modal */}
      <Modal isOpen={isDeptModalOpen} onClose={() => setIsDeptModalOpen(false)} title="Create New Department" maxWidth="440px">
        <form onSubmit={handleCreateDepartment} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Department Code *</label>
            <input
              type="text"
              required
              value={newDeptCode}
              onChange={(e) => setNewDeptCode(e.target.value.toUpperCase())}
              className="input-field"
              placeholder="e.g. WH, PUR, SALES"
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.35rem' }}>Department Name *</label>
            <input
              type="text"
              required
              value={newDeptName}
              onChange={(e) => setNewDeptName(e.target.value)}
              className="input-field"
              placeholder="Warehouse & Inventory Logistics"
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem' }}>
            <button type="button" onClick={() => setIsDeptModalOpen(false)} className="btn btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn btn-primary">
              Save Department
            </button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
