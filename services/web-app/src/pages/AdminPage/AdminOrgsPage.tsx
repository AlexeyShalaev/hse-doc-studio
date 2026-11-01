import { Navigate, Route, Routes, useNavigate, useParams } from "react-router";
import { OrgDetail, OrgsList } from "@features/admin-orgs";

const BASE = "/admin/orgs";

const List = () => {
  const navigate = useNavigate();
  return (
    <OrgsList
      onOpen={(slug) => {
        void navigate(`${BASE}/${encodeURIComponent(slug)}`);
      }}
    />
  );
};

const Detail = () => {
  const navigate = useNavigate();
  const { slug = "" } = useParams<{ slug: string }>();
  if (slug === "") return <Navigate to={BASE} replace />;
  const toList = () => {
    void navigate(BASE);
  };
  return (
    <OrgDetail key={slug} slug={slug} onBack={toList} onDeleted={toList} />
  );
};

/** Раздел «Организации» админки: список и страница организации. */
export const AdminOrgsPage = () => (
  <Routes>
    <Route index element={<List />} />
    <Route path=":slug" element={<Detail />} />
  </Routes>
);
